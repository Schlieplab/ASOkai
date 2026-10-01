#!/usr/bin/env python
"""
Filename: tests/unit/test_plan.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Tests for goal-driven pipeline planning.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

from pathlib import Path
from typing import cast
from unittest.mock import patch

import pytest

from ASOkai.Plugins import (
    FastaFile,
    FileInput,
    FileOutput,
    FileType,
    Runnable,
    RunSpec,
    ScalarParam,
    Step,
    StepSpec,
)
from ASOkai._pipeline.contracts.execution import (
    StepInputBinding,
    StepRun,
    StepRunOutput,
)
from ASOkai._pipeline.contracts.run_spec import FromRun
from ASOkai._pipeline.contracts.paths import (
    InputConfigField,
    OutputPathTemplate,
    TemplateField,
)
from ASOkai._pipeline.base import expand_runnable_steps
from ASOkai._pipeline.plan import _validated_run_specs, build_export_plan, build_plan
from ASOkai._pipeline.output_receipts import record_validated_outputs
from ASOkai._pipeline.tasks.base import Task


def _make_step(
    name: str,
    dependencies: list[Step] | None = None,
    *,
    output_names: list[str] | None = None,
    compatible_with: dict[str, list[str]] | None = None,
) -> Step:
    """Return a minimal concrete step for planner tests."""
    outputs = [
        FileOutput(
            output_name,
            destination=f"{name}/{output_name}.txt",
        )
        for output_name in output_names or [f"{name.replace('-', '_')}_out"]
    ]
    spec = StepSpec(
        inputs=[
            FileInput(
                dependency.spec.outputs[0].name,
                source=dependency.spec.outputs[0],
            )
            for dependency in dependencies or []
        ],
        outputs=outputs,
        compatible_with=compatible_with or {},
    )

    step_type = type(
        f"_{name.replace('-', '_').title()}Step",
        (Step,),
        {
            "name": name,
            "description": "",
            "spec": spec,
            **{f"{output.name}_output": output for output in outputs},
        },
    )
    return step_type()


def _make_parameter_step() -> Step:
    output = FileOutput(
        "result",
        destination=OutputPathTemplate(
            "results/{mode}.txt",
            fields={"mode": TemplateField("shared.mode")},
        ),
    )
    step_type = type(
        "_ParameterizedStep",
        (Step,),
        {
            "name": "parameterized",
            "description": "",
            "result_output": output,
            "spec": StepSpec(
                params=[
                    ScalarParam("mode", str, config="shared.mode"),
                    ScalarParam("local", int, default=5),
                ],
                outputs=[output],
            ),
        },
    )
    return step_type()


def _make_fasta_producer_and_consumer(*, gzip: bool = False) -> tuple[Step, Step]:
    output = FileOutput(
        "reference",
        destination="references/reference.fa",
        file_type=FastaFile(gzip=gzip),
    )
    producer_type = type(
        "_FastaProducer",
        (Step,),
        {
            "name": "fasta-producer",
            "description": "",
            "reference_output": output,
            "spec": StepSpec(outputs=[output]),
        },
    )
    consumer_output = FileOutput("result", destination="results/result.txt")
    consumer_type = type(
        "_FastaConsumer",
        (Step,),
        {
            "name": "fasta-consumer",
            "description": "",
            "result_output": consumer_output,
            "spec": StepSpec(
                inputs=[FileInput("reference", file_type=FastaFile())],
                outputs=[consumer_output],
            ),
        },
    )
    return producer_type(), consumer_type()


def _make_named_task(*, open_left_input: bool = False) -> tuple[Task, Step, Step]:
    source_output = FileOutput(
        "result",
        destination=OutputPathTemplate(
            "sources/{mode}.txt",
            fields={"mode": TemplateField("source.mode")},
        ),
    )
    source_type = type(
        "_TaskSourceStep",
        (Step,),
        {
            "name": "task-source",
            "description": "",
            "result_output": source_output,
            "spec": StepSpec(
                params=[ScalarParam("mode", str, config="source.mode")],
                outputs=[source_output],
            ),
        },
    )
    consumer_output = FileOutput(
        "result",
        destination=OutputPathTemplate(
            "results/{mode}.txt",
            fields={"mode": InputConfigField("input", "source.mode")},
        ),
    )
    consumer_type = type(
        "_TaskConsumerStep",
        (Step,),
        {
            "name": "task-consumer",
            "description": "",
            "result_output": consumer_output,
            "spec": StepSpec(
                inputs=[FileInput("input", file_type=FileType())],
                outputs=[consumer_output],
            ),
        },
    )
    source = source_type()
    consumer = consumer_type()
    task_type = type(
        "_LinkedTask",
        (Task,),
        {
            "name": "linked-task",
            "description": "Connects two specific producer runs.",
            "runs": (
                RunSpec(
                    "left_result",
                    consumer,
                    inputs=(
                        {}
                        if open_left_input
                        else {"input": {"from": "run.left_source.result"}}
                    ),
                ),
                RunSpec(
                    "right_result",
                    consumer,
                    inputs={"input": {"from": "run.right_source.result"}},
                ),
                RunSpec("left_source", source, parameters={"mode": "left"}),
                RunSpec("right_source", source, parameters={"mode": "right"}),
            ),
            "outputs": {"left": FromRun("left_source", "result")},
        },
    )
    return task_type(), source, consumer


def _make_configurable_task() -> tuple[Task, Step]:
    step = _make_parameter_step()
    task_type = type(
        "_ConfigurableTask",
        (Task,),
        {
            "name": "configurable-task",
            "description": "Selects two runs of one step.",
            "runs": (
                RunSpec("selected", step),
                RunSpec("fixed", step, parameters={"mode": "fixed"}),
            ),
        },
    )
    return task_type(), step


def _materialize_run(run: StepRun) -> StepRun:
    """Materialize and receipt one already resolved concrete run."""
    for path in run.output_paths().values():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    run.validate_output_files()
    record_validated_outputs(run)
    return run


def _materialize_outputs(step: Step, config: dict) -> StepRun:
    """Materialize and receipt one inputless test step."""
    return _materialize_run(StepRun(step.name, step, config))


def _run_with_producer(step: Step, producer: Step, config: dict) -> StepRun:
    """Return a concrete run bound to its declared producer output."""
    producer_run = StepRun(producer.name, producer, config)
    return StepRun(
        step.name,
        step,
        config,
        inputs=(
            StepInputBinding(
                step.spec.inputs[0],
                producer_run.output(producer.spec.outputs[0]),
            ),
        ),
    )


def test_planner_rejects_an_outputless_step(config):
    outputless_type = type(
        "_OutputlessStep",
        (Step,),
        {
            "name": "outputless",
            "description": "Invalid outputless step.",
            "spec": StepSpec(),
        },
    )
    step = outputless_type()

    with pytest.raises(ValueError, match="at least one file output"):
        build_plan([step], config, _registry={step.name: step})


def test_planner_rejects_unknown_configured_step_name(config):
    step = _make_step("known-step")
    config["steps"] = {"misspelled-step": {"inputs": {}}}

    with pytest.raises(ValueError, match=r"steps\.misspelled-step.*unknown"):
        build_plan([step], config, _registry={step.name: step})


def test_configured_runs_keep_order_and_resolve_parameter_fallback(config):
    step = _make_parameter_step()
    config["shared"] = {"mode": "fast"}
    config["runs"] = [
        {"step": step.name, "parameters": {"local": 7}},
        {"step": step.name, "parameters": {"mode": "slow"}},
    ]

    plan = build_plan([], config, _registry={step.name: step})

    assert [run.run_id for run in plan.goals] == ["runs.1", "runs.2"]
    assert [run.parameters for run in plan.goals] == [
        {"mode": "fast", "local": 7},
        {"mode": "slow", "local": 5},
    ]
    assert [run.output_paths()["result"] for run in plan.goals] == [
        Path(config["datadir"]) / "results/fast.txt",
        Path(config["datadir"]) / "results/slow.txt",
    ]
    assert _scheduled_run_ids(plan) == ["runs.1", "runs.2"]
    assert config["shared"]["mode"] == "fast"


def test_cli_and_config_selections_normalize_to_run_specs(config):
    producer, consumer = _make_configurable_producer_and_consumer()
    registry = {producer.name: producer, consumer.name: consumer}

    _, cli_specs = _validated_run_specs([producer], config, registry, None, None)
    assert len(cli_specs) == 1
    assert isinstance(cli_specs[0], RunSpec)
    assert cli_specs[0].run_id == producer.name
    assert cli_specs[0].step is producer

    config["runs"] = [
        {
            "step": consumer.name,
            "inputs": {"result": {"from": "run.source.result"}},
        },
        {"id": "source", "step": producer.name, "parameters": {"mode": "alt"}},
    ]
    _, configured_specs = _validated_run_specs([], config, registry, None, None)
    assert all(isinstance(spec, RunSpec) for spec in configured_specs)
    assert [spec.run_id for spec in configured_specs] == ["runs.1", "runs.source"]
    assert configured_specs[0].inputs == {
        "result": FromRun("runs.source", "result")
    }
    assert configured_specs[1].parameters == {"mode": "alt"}


def test_from_reference_links_named_step_declared_later(config):
    producer, consumer = _make_configurable_producer_and_consumer()
    config["shared"] = {"mode": "base"}
    config["runs"] = [
        {
            "step": consumer.name,
            "inputs": {"result": {"from": "run.source.result"}},
        },
        {"step": producer.name, "id": "source", "parameters": {"mode": "alt"}},
    ]

    plan = build_export_plan(
        [],
        config,
        recursive=True,
        _registry={producer.name: producer, consumer.name: consumer},
    )

    selected = plan.goals[0].inputs[0].source
    assert isinstance(selected, StepRunOutput)
    assert selected.run is plan.goals[1]


def test_equivalent_configured_runs_share_one_execution(config):
    step = _make_parameter_step()
    config["shared"] = {"mode": "fast"}
    config["runs"] = [
        {"step": step.name},
        {"step": step.name, "parameters": {"mode": "fast"}},
    ]

    plan = build_plan([], config, _registry={step.name: step})

    assert len(plan.goals) == 2
    assert plan.goals[0] is plan.goals[1]
    assert _scheduled_run_ids(plan) == ["runs.1"]


def test_reused_run_cannot_share_an_output_path_with_another_run(config):
    step = _make_parameter_step()
    config["shared"] = {"mode": "fast"}
    _materialize_run(StepRun("previous", step, config, parameters={"local": 5}))
    config["runs"] = [
        {"step": step.name, "parameters": {"local": 5}},
        {"step": step.name, "parameters": {"local": 7}},
    ]

    with pytest.raises(ValueError, match="Output path collision"):
        build_plan([], config, _registry={step.name: step})


def test_configured_run_parameters_are_validated(config):
    step = _make_parameter_step()
    config["runs"] = [{"step": step.name, "parameters": {"mode": 3}}]

    with pytest.raises(ValueError, match="parameter 'mode'"):
        build_plan([], config, _registry={step.name: step})


def test_configured_run_supplies_parameter_without_global_binding(config):
    output = FileOutput("result", destination="required/result.txt")
    step_type = type(
        "_RequiredParameterStep",
        (Step,),
        {
            "name": "required-parameter",
            "description": "",
            "result_output": output,
            "spec": StepSpec(params=[ScalarParam("count", int)], outputs=[output]),
        },
    )
    step = step_type()
    config["runs"] = [{"step": step.name, "parameters": {"count": 21}}]

    plan = build_plan([], config, _registry={step.name: step})
    assert plan.goals[0].parameters["count"] == 21

    config["runs"] = [{"step": step.name}]
    with pytest.raises(ValueError, match="requires a value"):
        build_plan([], config, _registry={step.name: step})


def test_configured_task_expands_its_steps_in_order(config):
    first = _make_step("first")
    second = _make_step("second", [first])

    class FakeTask:
        name = "two-step-task"
        description = ""
        steps = (first, second)

    config["runs"] = [{"task": FakeTask.name}]
    plan = build_plan(
        [],
        config,
        _registry={step.name: step for step in (first, second)},
        _tasks={FakeTask.name: cast(Task, FakeTask())},
    )

    assert [run.run_id for run in plan.goals] == [
        "runs.1.first",
        "runs.1.second",
    ]
    assert _scheduled_run_ids(plan) == ["runs.1.first", "runs.1.second"]


def test_legacy_task_general_parameter_applies_to_matching_step(config):
    step = _make_parameter_step()

    class LegacyTask:
        name = "legacy-task"
        description = "Selects one step."
        steps = (step,)

    config["runs"] = [{"task": LegacyTask.name, "parameters": {"mode": "task"}}]
    plan = build_plan(
        [],
        config,
        _registry={step.name: step},
        _tasks={LegacyTask.name: cast(Task, LegacyTask())},
    )

    assert plan.goals[0].parameters["mode"] == "task"


@pytest.mark.parametrize("selection", ["task", "yaml", "workflow"])
@pytest.mark.parametrize("export", [False, True])
def test_named_task_runs_keep_local_links_and_repeated_steps(config, selection, export):
    task, source, consumer = _make_named_task()
    config["source"] = {"mode": "shared"}
    prefix = "runs.1" if selection == "yaml" else task.name
    if selection == "yaml":
        config["runs"] = [{"task": task.name}]
        runnables = []
    elif selection == "workflow":
        workflow_type = type(
            "_TaskWorkflow",
            (),
            {"name": "task-workflow", "description": "", "members": (task,)},
        )
        runnables = [cast(Runnable, workflow_type())]
    else:
        runnables = [cast(Runnable, task)]

    build = build_export_plan if export else build_plan
    plan = build(
        runnables,
        config,
        _registry={source.name: source, consumer.name: consumer},
        _tasks={task.name: cast(Task, task)},
    )

    assert [run.run_id for run in plan.goals] == [
        f"{prefix}.left_result",
        f"{prefix}.right_result",
        f"{prefix}.left_source",
        f"{prefix}.right_source",
    ]
    assert _scheduled_run_ids(plan) == [
        f"{prefix}.left_source",
        f"{prefix}.right_source",
        f"{prefix}.left_result",
        f"{prefix}.right_result",
    ]
    for consumer_run, source_run in zip(plan.goals[:2], plan.goals[2:]):
        selected = consumer_run.inputs[0].source
        assert isinstance(selected, StepRunOutput)
        assert selected.run is source_run
        assert (
            consumer_run.output_paths()["result"].stem == source_run.parameters["mode"]
        )


@pytest.mark.parametrize("export", [False, True])
def test_task_general_parameters_and_child_overrides(config, export):
    task, step = _make_configurable_task()
    config["shared"] = {"mode": "global"}
    config["runs"] = [
        {
            "task": task.name,
            "id": "first",
            "parameters": {"mode": "left"},
        },
        {
            "task": task.name,
            "id": "second",
            "parameters": {"mode": "right"},
        },
    ]

    build = build_export_plan if export else build_plan
    plan = build([], config, _registry={step.name: step}, _tasks={task.name: task})

    assert [run.parameters["mode"] for run in plan.goals] == [
        "left",
        "fixed",
        "right",
        "fixed",
    ]
    assert plan.goals[1] is plan.goals[3]
    assert {run.output_paths()["result"].stem for run in plan.runs_to_execute} == {
        "left",
        "right",
        "fixed",
    }


def test_task_uses_shared_config_when_general_parameter_is_omitted(config):
    task, step = _make_configurable_task()
    config["shared"] = {"mode": "global"}

    plan = build_plan([task], config, _registry={step.name: step})

    assert [run.parameters["mode"] for run in plan.goals] == ["global", "fixed"]


def test_task_child_override_changes_only_named_run(config):
    task, step = _make_configurable_task()
    config["shared"] = {"mode": "global"}
    config["runs"] = [
        {
            "task": task.name,
            "runs": [{"id": "selected", "parameters": {"mode": "child"}}],
        }
    ]

    plan = build_plan([], config, _registry={step.name: step}, _tasks={task.name: task})

    assert [run.parameters["mode"] for run in plan.goals] == ["child", "fixed"]


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ([{"id": "missing", "parameters": {"mode": "left"}}], "unknown task run"),
        ([{"id": "selected"}, {"id": "selected"}], "duplicate task run"),
        ([{"id": "selected", "parameters": {"unknown": "left"}}], "unknown parameter"),
        ([{"id": "selected", "parameters": {"mode": 21}}], "must be str"),
        ([{"id": "fixed", "parameters": {"mode": "changed"}}], "task-declared"),
    ],
)
def test_task_rejects_invalid_child_run_ids(config, overrides, message):
    task, step = _make_configurable_task()
    config["runs"] = [{"task": task.name, "runs": overrides}]

    with pytest.raises(ValueError, match=message):
        build_plan([], config, _registry={step.name: step}, _tasks={task.name: task})


def test_task_child_input_can_link_to_top_level_named_run(config):
    task, source, consumer = _make_named_task(open_left_input=True)
    config["source"] = {"mode": "shared"}
    config["runs"] = [
        {
            "task": task.name,
            "id": "analysis",
            "runs": [
                {
                    "id": "left_result",
                    "inputs": {"input": {"from": "run.outside.result"}},
                }
            ],
        },
        {"step": source.name, "id": "outside", "parameters": {"mode": "outside"}},
    ]

    plan = build_plan(
        [],
        config,
        _registry={source.name: source, consumer.name: consumer},
        _tasks={task.name: task},
    )

    assert plan.goals[0].run_id == "runs.analysis.left_result"
    binding = plan.goals[0].inputs[0].source
    assert isinstance(binding, StepRunOutput)
    assert binding.run is plan.goals[-1]


def test_task_declared_path_supplies_fixed_child_input(config, tmp_path):
    producer = _make_step("fixed-path-producer")
    consumer = _make_step("fixed-path-consumer", [producer])
    input_name = producer.spec.outputs[0].name
    selected_path = tmp_path / "selected.txt"
    selected_path.write_text("selected")
    task_type = type(
        "_FixedPathTask",
        (Task,),
        {
            "name": "fixed-path-task",
            "description": "Uses a declared input file.",
            "runs": (
                RunSpec("consumer", consumer, inputs={input_name: selected_path}),
            ),
        },
    )
    task = task_type()
    config["runs"] = [{"task": task.name}]

    plan = build_plan(
        [],
        config,
        _registry={producer.name: producer, consumer.name: consumer},
        _tasks={task.name: task},
    )

    assert _scheduled_run_ids(plan) == ["runs.1.consumer"]
    assert plan.goals[0].input_paths()[input_name] == selected_path


@pytest.mark.parametrize(
    "selection",
    [
        {"from": "run.outside.result"},
        {"path": "/tmp/alternate-result.txt"},
    ],
)
def test_task_declared_input_cannot_be_overridden(config, selection):
    task, source, consumer = _make_named_task()
    config["source"] = {"mode": "shared"}
    config["runs"] = [
        {
            "task": task.name,
            "runs": [{"id": "left_result", "inputs": {"input": selection}}],
        }
    ]

    with pytest.raises(ValueError, match="cannot override task-declared input"):
        build_plan(
            [],
            config,
            _registry={source.name: source, consumer.name: consumer},
            _tasks={task.name: task},
        )


def test_top_level_run_can_link_to_named_task_child(config):
    task, source, consumer = _make_named_task()
    config["source"] = {"mode": "shared"}
    config["runs"] = [
        {
            "step": consumer.name,
            "id": "outside-consumer",
            "inputs": {"input": {"from": "run.analysis.right_source.result"}},
        },
        {"task": task.name, "id": "analysis"},
    ]

    plan = build_plan(
        [],
        config,
        _registry={source.name: source, consumer.name: consumer},
        _tasks={task.name: task},
    )

    binding = plan.goals[0].inputs[0].source
    assert isinstance(binding, StepRunOutput)
    assert binding.run.run_id == "runs.analysis.right_source"


@pytest.mark.parametrize("export", [False, True])
def test_from_reference_resolves_public_task_output_declared_later(config, export):
    task, source, consumer = _make_named_task()
    config["source"] = {"mode": "shared"}
    config["runs"] = [
        {
            "step": consumer.name,
            "inputs": {"input": {"from": "run.analysis.left"}},
        },
        {"task": task.name, "id": "analysis"},
    ]

    build = build_export_plan if export else build_plan
    plan = build(
        [],
        config,
        _registry={source.name: source, consumer.name: consumer},
        _tasks={task.name: task},
    )

    selected = plan.goals[0].inputs[0].source
    assert isinstance(selected, StepRunOutput)
    assert selected.run is plan.goals[3]  # analysis.left_source
    assert selected.output.name == "result"


def test_task_run_input_accepts_from_reference(config):
    task, source, consumer = _make_named_task(open_left_input=True)
    config["source"] = {"mode": "shared"}
    config["runs"] = [
        {
            "task": task.name,
            "runs": [
                {
                    "id": "left_result",
                    "inputs": {"input": {"from": "run.left_source.result"}},
                }
            ],
        }
    ]

    plan = build_plan(
        [],
        config,
        _registry={source.name: source, consumer.name: consumer},
        _tasks={task.name: task},
    )
    selected = plan.goals[0].inputs[0].source
    assert isinstance(selected, StepRunOutput)
    assert selected.run is plan.goals[2]


@pytest.mark.parametrize(
    ("parameters", "message"),
    [
        ({"unknown": "left"}, "unknown parameter"),
        ({"mode": 21}, "must be str"),
    ],
)
def test_task_selection_rejects_invalid_parameter_values(config, parameters, message):
    task, step = _make_configurable_task()
    config["runs"] = [{"task": task.name, "parameters": parameters}]

    with pytest.raises(ValueError, match=message):
        build_plan([], config, _registry={step.name: step}, _tasks={task.name: task})


@pytest.mark.parametrize("kind", ["step", "task"])
def test_configured_runs_reject_unknown_selections(config, kind):
    config["runs"] = [{kind: "missing"}]

    with pytest.raises(ValueError, match=rf"\$\.runs\[0\]\.{kind}: unknown"):
        build_plan([], config, _registry={}, _tasks={})


def test_configured_runs_cannot_mix_with_explicit_selections(config):
    step = _make_step("first")
    config["runs"] = [{"step": step.name}]

    with pytest.raises(ValueError, match="not both"):
        build_plan([step], config, _registry={step.name: step})


def test_named_run_input_link_resolves_forward_reference_before_consumer(config):
    producer, consumer = _make_configurable_producer_and_consumer()
    config["producer"] = {"mode": "main"}
    config["steps"] = {
        consumer.name: {
            "inputs": {
                "result": {"path_override": str(Path(config["datadir"]) / "missing")}
            }
        }
    }
    config["runs"] = [
        {
            "step": consumer.name,
            "inputs": {"result": {"from": "run.alternate.result"}},
        },
        {
            "id": "alternate",
            "step": producer.name,
            "parameters": {"mode": "alternate"},
        },
    ]

    plan = build_plan(
        [], config, _registry={producer.name: producer, consumer.name: consumer}
    )

    assert [run.run_id for run in plan.goals] == ["runs.1", "runs.alternate"]
    assert _scheduled_run_ids(plan) == ["runs.alternate", "runs.1"]
    source = plan.goals[0].inputs[0].source
    assert isinstance(source, StepRunOutput)
    assert source.run is plan.goals[1]
    assert source.run.parameters["mode"] == "alternate"


def test_configured_run_external_path_replaces_global_input(config, tmp_path):
    producer, consumer = _make_configurable_producer_and_consumer()
    selected_path = tmp_path / "selected.txt"
    selected_path.write_text("selected")
    config["producer"] = {"mode": "main"}
    config["steps"] = {
        consumer.name: {
            "inputs": {"result": {"path_override": str(tmp_path / "missing.txt")}}
        }
    }
    config["runs"] = [
        {"step": consumer.name, "inputs": {"result": {"path": str(selected_path)}}}
    ]

    plan = build_plan(
        [], config, _registry={producer.name: producer, consumer.name: consumer}
    )

    assert _scheduled_run_ids(plan) == ["runs.1"]
    assert plan.goals[0].input_paths()["result"] == selected_path
    assert plan.goals[0].inputs[0].selection_path == "$.runs[0].inputs.result.path"


def test_configured_run_external_path_is_validated(config, tmp_path):
    producer, consumer = _make_configurable_producer_and_consumer()
    config["producer"] = {"mode": "main"}
    config["runs"] = [
        {
            "step": consumer.name,
            "inputs": {"result": {"path": str(tmp_path / "missing.txt")}},
        }
    ]

    with pytest.raises(ValueError, match=r"runs\[0\].*file does not exist"):
        build_plan(
            [], config, _registry={producer.name: producer, consumer.name: consumer}
        )


@pytest.mark.parametrize("export", [False, True])
def test_distinct_runs_cannot_publish_to_the_same_path(config, tmp_path, export):
    producer, consumer = _make_configurable_producer_and_consumer()
    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"
    first.write_text("first")
    second.write_text("second")
    config["producer"] = {"mode": "main"}
    config["runs"] = [
        {
            "id": "first",
            "step": consumer.name,
            "inputs": {"result": {"path": str(first)}},
        },
        {
            "id": "second",
            "step": consumer.name,
            "inputs": {"result": {"path": str(second)}},
        },
    ]

    build = build_export_plan if export else build_plan
    with pytest.raises(ValueError, match="Output path collision") as error:
        build([], config, _registry={producer.name: producer, consumer.name: consumer})

    assert "runs.first.consumer_out" in str(error.value)
    assert "runs.second.consumer_out" in str(error.value)
    assert str(Path(config["datadir"]) / "consumer.txt") in str(error.value)


def test_typed_input_accepts_compatible_named_producer(config):
    producer, consumer = _make_fasta_producer_and_consumer()
    config["runs"] = [
        {"id": "source", "step": producer.name},
        {
            "step": consumer.name,
            "inputs": {"reference": {"from": "run.source.reference"}},
        },
    ]

    plan = build_plan(
        [], config, _registry={producer.name: producer, consumer.name: consumer}
    )

    source = plan.goals[1].inputs[0].source
    assert isinstance(source, StepRunOutput)
    assert source.run is plan.goals[0]


def test_typed_input_rejects_incompatible_named_producer(config):
    producer, consumer = _make_fasta_producer_and_consumer(gzip=True)
    config["runs"] = [
        {"id": "compressed", "step": producer.name},
        {
            "step": consumer.name,
            "inputs": {"reference": {"from": "run.compressed.reference"}},
        },
    ]

    with pytest.raises(ValueError, match="incompatible"):
        build_plan(
            [], config, _registry={producer.name: producer, consumer.name: consumer}
        )


def test_typed_input_requires_explicit_source(config):
    _, consumer = _make_fasta_producer_and_consumer()
    config["runs"] = [{"step": consumer.name}]

    with pytest.raises(ValueError, match="requires a path or a named producer"):
        build_plan([], config, _registry={consumer.name: consumer})


@pytest.mark.parametrize(
    ("runs", "message"),
    [
        (
            [{"id": "same", "step": "producer"}, {"id": "same", "step": "producer"}],
            "duplicate run id",
        ),
        (
            [
                {
                    "step": "consumer",
                    "inputs": {"result": {"from": "run.missing.result"}},
                }
            ],
            "unknown named run",
        ),
        (
            [
                {"id": "source", "step": "producer"},
                {
                    "step": "consumer",
                    "inputs": {"result": {"from": "run.source.missing"}},
                },
            ],
            "has no output",
        ),
    ],
)
def test_configured_run_links_reject_bad_references(config, runs, message):
    producer, consumer = _make_configurable_producer_and_consumer()
    config["producer"] = {"mode": "main"}
    config["runs"] = runs

    with pytest.raises(ValueError, match=message):
        build_plan(
            [], config, _registry={producer.name: producer, consumer.name: consumer}
        )


def test_configured_run_links_reject_cycles(config):
    output = FileOutput("result", destination="result.txt")
    step_type = type(
        "_SelfReferencingStep",
        (Step,),
        {
            "name": "self-referencing",
            "description": "",
            "result_output": output,
            "spec": StepSpec(
                inputs=[FileInput("input", file_type=FileType())],
                outputs=[output],
            ),
        },
    )
    step = step_type()
    config["runs"] = [
        {
            "id": "loop",
            "step": step.name,
            "inputs": {"input": {"from": "run.loop.result"}},
        }
    ]

    with pytest.raises(ValueError, match="Dependency cycle"):
        build_plan([], config, _registry={step.name: step})


def _make_configurable_producer_and_consumers(
    *consumer_names: str,
    input_names: tuple[str, ...] = ("result",),
) -> tuple[Step, list[Step]]:
    """Return consumers of a producer with a selectable mode parameter."""
    output = FileOutput(
        "result",
        destination=OutputPathTemplate(
            "{mode}/result.txt",
            fields={"mode": TemplateField("producer.mode")},
        ),
    )
    producer_type = type(
        "_ConfiguredProducerStep",
        (Step,),
        {
            "name": "producer",
            "description": "",
            "result_output": output,
            "spec": StepSpec(
                params=[ScalarParam("mode", str, config="producer.mode")],
                outputs=[output],
            ),
        },
    )
    producer = producer_type()

    consumers: list[Step] = []
    for consumer_name in consumer_names:
        consumer_output = FileOutput(
            f"{consumer_name}_out",
            destination=f"{consumer_name}.txt",
        )
        consumer_type = type(
            f"_{consumer_name.title()}ConsumerStep",
            (Step,),
            {
                "name": consumer_name,
                "description": "",
                f"{consumer_name}_out_output": consumer_output,
                "spec": StepSpec(
                    inputs=[
                        FileInput(
                            input_name,
                            source=output,
                        )
                        for input_name in input_names
                    ],
                    outputs=[consumer_output],
                ),
            },
        )
        consumers.append(consumer_type())
    return producer, consumers


def _make_configurable_producer_and_consumer() -> tuple[Step, Step]:
    """Return one consumer of a parameterized producer."""
    producer, consumers = _make_configurable_producer_and_consumers("consumer")
    return producer, consumers[0]


@pytest.fixture
def config(tmp_path):
    return {"datadir": str(tmp_path)}


def _scheduled_run_ids(plan) -> list[str]:
    return [run.run_id for run in plan.runs_to_execute]


def test_missing_goal_is_scheduled(config):
    step = _make_step("alpha")

    plan = build_plan([step], config, _registry={step.name: step})

    assert _scheduled_run_ids(plan) == ["alpha"]
    assert [run.run_id for run in plan.goals] == ["alpha"]
    assert plan.resolved_outputs == {}


def test_unreceipted_goal_output_is_scheduled(config):
    step = _make_step("alpha")
    output_path = StepRun(step.name, step, config).output_paths()["alpha_out"]
    output_path.parent.mkdir(parents=True)
    output_path.touch()

    plan = build_plan([step], config, _registry={step.name: step})

    assert _scheduled_run_ids(plan) == ["alpha"]
    assert plan.resolved_outputs == {}


def test_changed_receipted_goal_output_is_scheduled(config):
    step = _make_step("alpha")
    run = _materialize_outputs(step, config)
    run.output_paths()["alpha_out"].write_text("changed", encoding="utf-8")

    plan = build_plan([step], config, _registry={step.name: step})

    assert _scheduled_run_ids(plan) == ["alpha"]
    assert plan.resolved_outputs == {}


def test_full_output_validation_reuses_valid_unreceipted_output(config):
    step = _make_step("alpha")
    output_path = StepRun(step.name, step, config).output_paths()["alpha_out"]
    output_path.parent.mkdir(parents=True)
    output_path.touch()
    config["validation"] = {"existing_outputs": "contract"}

    with patch.object(type(step.spec.outputs[0].file_type), "validate") as validate:
        plan = build_plan([step], config, _registry={step.name: step})

    assert plan.runs_to_execute == ()
    validate.assert_called_once_with(output_path)


def test_full_output_validation_schedules_invalid_output(config):
    step = _make_step("alpha")
    output_path = StepRun(step.name, step, config).output_paths()["alpha_out"]
    output_path.parent.mkdir(parents=True)
    output_path.touch()
    config["validation"] = {"existing_outputs": "contract"}

    with patch.object(
        type(step.spec.outputs[0].file_type),
        "validate",
        side_effect=ValueError("invalid contents"),
    ):
        plan = build_plan([step], config, _registry={step.name: step})

    assert _scheduled_run_ids(plan) == ["alpha"]
    assert plan.resolved_outputs == {}


def test_valid_goal_output_is_reused(config):
    step = _make_step(
        "alpha",
        output_names=["result"],
    )
    _materialize_outputs(step, config)

    plan = build_plan([step], config, _registry={step.name: step})

    assert plan.runs_to_execute == ()
    assert {
        (run_output.run.run_id, run_output.output.name)
        for run_output in plan.resolved_outputs
    } == {("alpha", "result")}


def test_force_schedules_valid_goal(config):
    step = _make_step("alpha")
    _materialize_outputs(step, config)

    plan = build_plan(
        [step],
        config,
        force=True,
        _registry={step.name: step},
    )

    assert _scheduled_run_ids(plan) == ["alpha"]
    assert plan.resolved_outputs == {}


@pytest.mark.parametrize("outputs_exist", [False, True])
def test_incompatible_goal_is_rejected_before_reuse(config, outputs_exist):
    step = _make_step(
        "restricted",
        compatible_with={"analysis.mode": ["supported"]},
    )
    if outputs_exist:
        _materialize_outputs(step, config)
    config["analysis"] = {"mode": "unsupported"}

    with pytest.raises(
        ValueError,
        match=r"analysis\.mode.*incompatible.*restricted.*supported",
    ):
        build_plan([step], config, _registry={step.name: step})


def test_missing_dependencies_are_resolved_automatically(config):
    dependency = _make_step("dependency")
    goal = _make_step("goal", [dependency])

    plan = build_plan(
        [goal],
        config,
        _registry={dependency.name: dependency, goal.name: goal},
    )

    assert _scheduled_run_ids(plan) == ["dependency", "goal"]
    binding = plan.goals[0].inputs[0]
    assert isinstance(binding.source, StepRunOutput)
    assert binding.source.run.run_id == "dependency"


def test_valid_dependency_is_reused(config):
    dependency = _make_step(
        "dependency",
        output_names=["result"],
    )
    _materialize_outputs(dependency, config)
    goal = _make_step("goal", [dependency])

    plan = build_plan(
        [goal],
        config,
        _registry={dependency.name: dependency, goal.name: goal},
    )

    assert _scheduled_run_ids(plan) == ["goal"]
    reused_output = plan.goals[0].inputs[0].source
    assert isinstance(reused_output, StepRunOutput)
    assert plan.resolved_outputs[reused_output].name == "result.txt"


def test_reused_goal_does_not_require_its_missing_dependencies(config):
    dependency = _make_step("dependency")
    goal = _make_step("goal", [dependency])
    _materialize_run(_run_with_producer(goal, dependency, config))

    plan = build_plan(
        [goal],
        config,
        _registry={dependency.name: dependency, goal.name: goal},
    )

    assert plan.runs_to_execute == ()
    assert {output.run.run_id for output in plan.resolved_outputs} == {"goal"}


def test_reused_goal_requires_dependency_parameters_for_its_identity(config):
    dependency, goal = _make_configurable_producer_and_consumer()
    config["producer"] = {"mode": "main"}
    _materialize_run(_run_with_producer(goal, dependency, config))
    del config["producer"]

    with pytest.raises(ValueError, match="producer.mode"):
        build_plan(
            [goal],
            config,
            _registry={dependency.name: dependency, goal.name: goal},
        )


def test_dependency_chain_is_scheduled_in_topological_order(config):
    first = _make_step("first")
    second = _make_step("second", [first])
    goal = _make_step("goal", [second])

    plan = build_plan(
        [goal],
        config,
        _registry={step.name: step for step in (first, second, goal)},
    )

    assert _scheduled_run_ids(plan) == ["first", "second", "goal"]


def test_breadth_first_discovery_prioritizes_sibling_runs(config):
    deep = _make_step("deep")
    left = _make_step("left", [deep])
    right = _make_step("right")
    goal = _make_step("goal", [left, right])

    plan = build_plan(
        [goal],
        config,
        _registry={step.name: step for step in (deep, left, right, goal)},
    )

    assert _scheduled_run_ids(plan) == ["right", "deep", "left", "goal"]


def test_dependency_cycle_is_rejected(config):
    first = _make_step("first")
    second = _make_step("second", [first])
    type(first).spec = StepSpec(
        inputs=[FileInput("second_out", source=second.spec.output("second_out"))],
        outputs=first.spec.outputs,
    )

    with pytest.raises(ValueError, match="cycle"):
        build_plan(
            [first],
            config,
            _registry={first.name: first, second.name: second},
        )


def test_duplicate_goals_and_dependencies_share_one_run(config):
    shared = _make_step("shared")
    first = _make_step("first", [shared])
    second = _make_step("second", [shared])

    plan = build_plan(
        [first, second, first],
        config,
        _registry={step.name: step for step in (shared, first, second)},
    )

    assert _scheduled_run_ids(plan) == ["shared", "first", "second"]
    assert [run.run_id for run in plan.goals] == ["first", "second"]


def test_equal_port_names_from_different_runs_do_not_collide(config):
    first = _make_step("first", output_names=["result"])
    second = _make_step("second", output_names=["result"])
    _materialize_outputs(first, config)
    _materialize_outputs(second, config)

    plan = build_plan(
        [first, second],
        config,
        _registry={first.name: first, second.name: second},
    )

    assert len(plan.resolved_outputs) == 2
    assert {output.run.run_id for output in plan.resolved_outputs} == {
        "first",
        "second",
    }


def test_unknown_producer_is_rejected(config):
    missing = _make_step("missing")
    goal = _make_step("goal", [missing])

    with pytest.raises(ValueError, match="unknown producer 'missing'"):
        build_plan([goal], config, _registry={goal.name: goal})


def test_shadow_output_declaration_is_rejected(config):
    producer = _make_step("producer", output_names=["actual"])
    shadow = _make_step("producer", output_names=["missing"])
    goal = _make_step("goal", [shadow])

    with pytest.raises(ValueError, match="unknown output 'missing'"):
        build_plan(
            [goal],
            config,
            _registry={producer.name: producer, goal.name: goal},
        )


def test_non_recursive_reuses_valid_dependency(config):
    dependency = _make_step("dependency")
    _materialize_outputs(dependency, config)
    goal = _make_step("goal", [dependency])

    plan = build_plan(
        [goal],
        config,
        non_recursive=True,
        _registry={dependency.name: dependency, goal.name: goal},
    )

    assert _scheduled_run_ids(plan) == ["goal"]


def test_non_recursive_rejects_missing_dependency(config):
    dependency = _make_step("dependency")
    goal = _make_step("goal", [dependency])

    with pytest.raises(RuntimeError, match="Omit --non-recursive"):
        build_plan(
            [goal],
            config,
            non_recursive=True,
            _registry={dependency.name: dependency, goal.name: goal},
        )


def test_explicit_goal_may_run_in_non_recursive_mode(config):
    dependency = _make_step("dependency")
    goal = _make_step("goal", [dependency])

    plan = build_plan(
        [dependency, goal],
        config,
        non_recursive=True,
        _registry={dependency.name: dependency, goal.name: goal},
    )

    assert _scheduled_run_ids(plan) == ["dependency", "goal"]


def test_force_does_not_force_valid_dependency(config):
    dependency = _make_step("dependency")
    _materialize_outputs(dependency, config)
    goal_with_dependency = _make_step("goal", [dependency])

    plan = build_plan(
        [goal_with_dependency],
        config,
        force=True,
        _registry={
            dependency.name: dependency,
            goal_with_dependency.name: goal_with_dependency,
        },
    )

    assert _scheduled_run_ids(plan) == ["goal"]


def test_file_override_bypasses_dependency(config, tmp_path):
    dependency = _make_step("dependency")
    goal = _make_step(
        "goal",
        [dependency],
    )
    override = tmp_path / "override.txt"
    override.touch()
    config["steps"] = {
        "goal": {
            "inputs": {
                "dependency_out": {"path_override": str(override)},
            },
        },
    }

    plan = build_plan(
        [goal],
        config,
        non_recursive=True,
        _registry={dependency.name: dependency, goal.name: goal},
    )

    assert _scheduled_run_ids(plan) == ["goal"]
    assert plan.goals[0].inputs[0].source == override.resolve()


def test_named_producer_run_is_shared_by_two_consumers(config):
    producer, consumers = _make_configurable_producer_and_consumers(
        "first", "second"
    )
    config["producer"] = {"mode": "main"}
    config["runs"] = [
        {"id": "alternate", "step": "producer", "parameters": {"mode": "alternate"}},
        *(
            {
                "id": consumer.name,
                "step": consumer.name,
                "inputs": {"result": {"from": "run.alternate.result"}},
            }
            for consumer in consumers
        ),
    ]

    plan = build_plan(
        [],
        config,
        _registry={step.name: step for step in (producer, *consumers)},
    )

    assert _scheduled_run_ids(plan) == [
        "runs.alternate", "runs.first", "runs.second"
    ]
    first_source = plan.goals[1].inputs[0].source
    second_source = plan.goals[2].inputs[0].source
    assert isinstance(first_source, StepRunOutput)
    assert isinstance(second_source, StepRunOutput)
    assert first_source.run is second_source.run is plan.goals[0]
    assert first_source.run.parameters["mode"] == "alternate"


def test_one_consumer_links_two_differently_configured_named_runs(config):
    producer, consumers = _make_configurable_producer_and_consumers(
        "consumer", input_names=("first_result", "second_result")
    )
    consumer = consumers[0]
    config["producer"] = {"mode": "main"}
    config["runs"] = [
        {"id": "one", "step": "producer", "parameters": {"mode": "one"}},
        {"id": "two", "step": "producer", "parameters": {"mode": "two"}},
        {
            "step": "consumer",
            "inputs": {
                "first_result": {"from": "run.one.result"},
                "second_result": {"from": "run.two.result"},
            },
        },
    ]

    plan = build_plan(
        [],
        config,
        _registry={producer.name: producer, consumer.name: consumer},
    )

    assert _scheduled_run_ids(plan) == ["runs.one", "runs.two", "runs.3"]
    assert [
        binding.source.run.parameters["mode"]
        for binding in plan.goals[2].inputs
        if isinstance(binding.source, StepRunOutput)
    ] == ["one", "two"]


def test_task_steps_are_requested_goals(config):
    dependency = _make_step("dependency")
    goal = _make_step("goal", [dependency])

    class FakeTask:
        name = "task"
        description = ""
        steps = [dependency, goal]

    plan = build_plan(
        [cast(Runnable, FakeTask())],
        config,
        _registry={dependency.name: dependency, goal.name: goal},
    )

    assert [run.run_id for run in plan.goals] == ["dependency", "goal"]
    assert _scheduled_run_ids(plan) == ["dependency", "goal"]


def test_workflow_members_are_terminal_goals(config):
    shared = _make_step("shared")
    first = _make_step("first", [shared])
    second = _make_step("second", [shared])

    class FakeWorkflow:
        name = "workflow"
        description = ""
        members = [first, second]

    plan = build_plan(
        [cast(Runnable, FakeWorkflow())],
        config,
        _registry={step.name: step for step in (shared, first, second)},
    )

    assert [run.run_id for run in plan.goals] == ["first", "second"]
    assert _scheduled_run_ids(plan) == ["shared", "first", "second"]


def test_workflow_flattens_tasks_and_nested_workflows_in_order():
    first = _make_step("first")
    second = _make_step("second")

    class FakeTask:
        name = "task"
        description = ""
        steps = [first]

    class InnerWorkflow:
        name = "inner"
        description = ""
        members = [FakeTask()]

    class OuterWorkflow:
        name = "outer"
        description = ""
        members = [InnerWorkflow(), second]

    goals = expand_runnable_steps(cast(Runnable, OuterWorkflow()))

    assert [step.name for step in goals] == ["first", "second"]


def test_workflow_cycle_is_rejected():
    class SelfReferencingWorkflow:
        name = "loop"
        description = ""
        members: list[Runnable] = []

    workflow = SelfReferencingWorkflow()
    workflow.members = [cast(Runnable, workflow)]

    with pytest.raises(ValueError, match="cycle"):
        expand_runnable_steps(cast(Runnable, workflow))


def test_non_recursive_export_exposes_only_direct_dependency_boundary(config):
    source = _make_step("source")
    intermediate = _make_step("intermediate", [source])
    goal = _make_step("goal", [intermediate])

    plan = build_export_plan(
        [goal],
        config,
        _registry={step.name: step for step in (source, intermediate, goal)},
    )

    assert _scheduled_run_ids(plan) == ["goal"]
    goal_source = plan.goals[0].inputs[0].source
    assert isinstance(goal_source, StepRunOutput)
    transitive_source = goal_source.run.inputs[0].source
    assert isinstance(transitive_source, StepRunOutput)
    assert plan.resolved_outputs == {
        goal_source: goal_source.run.output_path(goal_source.output),
    }
    assert transitive_source not in plan.resolved_outputs


def test_recursive_export_includes_complete_producer_closure(config):
    source = _make_step("source")
    intermediate = _make_step("intermediate", [source])
    goal = _make_step("goal", [intermediate])

    plan = build_export_plan(
        [goal],
        config,
        recursive=True,
        _registry={step.name: step for step in (source, intermediate, goal)},
    )

    assert _scheduled_run_ids(plan) == ["source", "intermediate", "goal"]
    assert plan.resolved_outputs == {}
