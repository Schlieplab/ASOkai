#!/usr/bin/env python
"""
Filename: tests/unit/test_plan.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Tests for goal-driven pipeline planning.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import cast
from unittest.mock import patch

import pytest

from ASOkai.Plugins import (
    FileInput,
    FileOutput,
    Runnable,
    ScalarParam,
    Step,
    StepSpec,
)
from ASOkai._pipeline.contracts.execution import (
    StepInputBinding,
    StepRun,
    StepRunOutput,
)
from ASOkai._pipeline.contracts.paths import OutputPathTemplate, TemplateField
from ASOkai._pipeline.base import expand_runnable_steps
from ASOkai._pipeline.plan import build_export_plan, build_plan
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


def _make_configurable_producer_and_consumers(
    *consumer_names: str,
    input_names: tuple[str, ...] = ("result",),
) -> tuple[Step, list[Step]]:
    """Return consumers that can override one producer's mode parameter."""
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
                            configurable_parameters=("mode",),
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
    """Return one consumer with a configurable producer input."""
    producer, consumers = _make_configurable_producer_and_consumers("consumer")
    return producer, consumers[0]


def _configure_producer_modes(
    config: dict,
    consumer_modes: dict[str, str],
) -> None:
    """Configure the main producer mode and each consumer-specific mode."""
    config.update(
        {
            "producer": {"mode": "main"},
            "steps": {
                consumer_name: {
                    "inputs": {
                        "result": {
                            "parameters": {"mode": mode},
                        },
                    },
                }
                for consumer_name, mode in consumer_modes.items()
            },
        }
    )


def _make_nested_configurable_steps() -> tuple[Step, Step, Step]:
    """Return a three-step chain with configurable producer inputs."""
    source_output = FileOutput(
        "source_result",
        destination=OutputPathTemplate(
            "{profile}/source.txt",
            fields={"profile": TemplateField("source.profile")},
        ),
    )
    source_type = type(
        "_NestedSourceStep",
        (Step,),
        {
            "name": "source",
            "description": "",
            "source_result_output": source_output,
            "spec": StepSpec(
                params=[ScalarParam("profile", str, config="source.profile")],
                outputs=[source_output],
            ),
        },
    )

    producer_output = FileOutput(
        "producer_result",
        destination=OutputPathTemplate(
            "{mode}/producer.txt",
            fields={"mode": TemplateField("producer.mode")},
        ),
    )
    producer_type = type(
        "_NestedProducerStep",
        (Step,),
        {
            "name": "producer",
            "description": "",
            "producer_result_output": producer_output,
            "spec": StepSpec(
                params=[ScalarParam("mode", str, config="producer.mode")],
                inputs=[
                    FileInput(
                        "source_result",
                        source=source_output,
                        configurable_parameters=("profile",),
                    )
                ],
                outputs=[producer_output],
            ),
        },
    )

    consumer_output = FileOutput(
        "consumer_result",
        destination="consumer.txt",
    )
    consumer_type = type(
        "_NestedConsumerStep",
        (Step,),
        {
            "name": "consumer",
            "description": "",
            "consumer_result_output": consumer_output,
            "spec": StepSpec(
                inputs=[
                    FileInput(
                        "producer_result",
                        source=producer_output,
                        configurable_parameters=("mode",),
                    )
                ],
                outputs=[consumer_output],
            ),
        },
    )
    return source_type(), producer_type(), consumer_type()


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


def test_configured_producer_gets_a_dotted_run_id_and_derived_config(config):
    producer, consumer = _make_configurable_producer_and_consumer()
    _configure_producer_modes(config, {"consumer": "alternate"})

    plan = build_plan(
        [consumer],
        config,
        _registry={producer.name: producer, consumer.name: consumer},
    )

    assert _scheduled_run_ids(plan) == ["consumer.producer", "consumer"]
    configured_producer = plan.runs_to_execute[0]
    assert configured_producer.config["producer"]["mode"] == "alternate"
    assert config["producer"]["mode"] == "main"
    source = plan.goals[0].inputs[0].source
    assert isinstance(source, StepRunOutput)
    assert source.run is configured_producer


def test_matching_configured_producer_requests_share_one_run(config):
    producer, consumers = _make_configurable_producer_and_consumers(
        "first",
        "second",
    )
    first, second = consumers
    _configure_producer_modes(
        config,
        {consumer.name: "alternate" for consumer in consumers},
    )

    plan = build_plan(
        consumers,
        config,
        _registry={step.name: step for step in (producer, first, second)},
    )

    assert _scheduled_run_ids(plan) == ["first.producer", "first", "second"]
    first_source = plan.goals[0].inputs[0].source
    second_source = plan.goals[1].inputs[0].source
    assert isinstance(first_source, StepRunOutput)
    assert isinstance(second_source, StepRunOutput)
    assert first_source.run is second_source.run


def test_different_configured_producer_requests_keep_separate_runs(config):
    producer, consumers = _make_configurable_producer_and_consumers(
        "first",
        "second",
    )
    first, second = consumers
    _configure_producer_modes(
        config,
        {"first": "one", "second": "two"},
    )

    plan = build_plan(
        consumers,
        config,
        _registry={step.name: step for step in (producer, first, second)},
    )

    assert _scheduled_run_ids(plan) == [
        "first.producer",
        "second.producer",
        "first",
        "second",
    ]
    first_source = plan.goals[0].inputs[0].source
    second_source = plan.goals[1].inputs[0].source
    assert isinstance(first_source, StepRunOutput)
    assert isinstance(second_source, StepRunOutput)
    assert first_source.run is not second_source.run


def test_one_consumer_can_request_two_configurations_of_one_producer(config):
    producer, consumers = _make_configurable_producer_and_consumers(
        "consumer",
        input_names=("first_result", "second_result"),
    )
    consumer = consumers[0]
    config.update(
        {
            "producer": {"mode": "main"},
            "steps": {
                "consumer": {
                    "inputs": {
                        "first_result": {"parameters": {"mode": "one"}},
                        "second_result": {"parameters": {"mode": "two"}},
                    },
                },
            },
        }
    )

    plan = build_plan(
        [consumer],
        config,
        _registry={producer.name: producer, consumer.name: consumer},
    )

    assert _scheduled_run_ids(plan) == [
        "consumer.producer",
        "consumer.second_result.producer",
        "consumer",
    ]
    producer_runs = []
    for binding in plan.goals[0].inputs:
        assert isinstance(binding.source, StepRunOutput)
        producer_runs.append(binding.source.run)
    assert [run.config["producer"]["mode"] for run in producer_runs] == [
        "one",
        "two",
    ]


def test_main_request_names_an_equivalent_configured_producer_run(config):
    producer, consumer = _make_configurable_producer_and_consumer()
    _configure_producer_modes(config, {"consumer": "main"})

    plan = build_plan(
        [consumer, producer],
        config,
        _registry={producer.name: producer, consumer.name: consumer},
    )

    assert _scheduled_run_ids(plan) == ["producer", "consumer"]
    source = plan.goals[0].inputs[0].source
    assert isinstance(source, StepRunOutput)
    assert source.run is plan.goals[1]


def test_matching_reusable_producer_requests_share_one_run(config):
    producer, consumers = _make_configurable_producer_and_consumers(
        "first",
        "second",
    )
    _configure_producer_modes(
        config,
        {consumer.name: "alternate" for consumer in consumers},
    )
    producer_config = deepcopy(config)
    producer_config["producer"]["mode"] = "alternate"
    producer_run = _materialize_outputs(producer, producer_config)
    output_path = producer_run.output_paths()["result"]

    plan = build_plan(
        consumers,
        config,
        _registry={step.name: step for step in (producer, *consumers)},
    )

    assert _scheduled_run_ids(plan) == ["first", "second"]
    first_source = plan.goals[0].inputs[0].source
    second_source = plan.goals[1].inputs[0].source
    assert isinstance(first_source, StepRunOutput)
    assert isinstance(second_source, StepRunOutput)
    assert first_source.run is second_source.run
    assert plan.resolved_outputs[first_source] == output_path


def test_force_applies_to_a_shared_main_producer_run(config):
    producer, consumer = _make_configurable_producer_and_consumer()
    _configure_producer_modes(config, {"consumer": "main"})
    _materialize_outputs(producer, config)

    plan = build_plan(
        [consumer, producer],
        config,
        force=True,
        _registry={producer.name: producer, consumer.name: consumer},
    )

    assert _scheduled_run_ids(plan) == ["producer", "consumer"]
    source = plan.goals[0].inputs[0].source
    assert isinstance(source, StepRunOutput)
    assert source.run is plan.goals[1]
    assert source not in plan.resolved_outputs


def test_non_recursive_recognizes_a_shared_main_producer_as_a_goal(config):
    producer, consumer = _make_configurable_producer_and_consumer()
    _configure_producer_modes(config, {"consumer": "main"})

    plan = build_plan(
        [consumer, producer],
        config,
        non_recursive=True,
        _registry={producer.name: producer, consumer.name: consumer},
    )

    assert _scheduled_run_ids(plan) == ["producer", "consumer"]


def test_existing_configured_producer_output_is_reused(config):
    producer, consumer = _make_configurable_producer_and_consumer()
    _configure_producer_modes(config, {"consumer": "alternate"})
    producer_config = deepcopy(config)
    producer_config["producer"]["mode"] = "alternate"
    producer_run = _materialize_outputs(producer, producer_config)
    configured_output = producer_run.output_paths()["result"]

    plan = build_plan(
        [consumer],
        config,
        non_recursive=True,
        _registry={producer.name: producer, consumer.name: consumer},
    )

    assert _scheduled_run_ids(plan) == ["consumer"]
    source = plan.goals[0].inputs[0].source
    assert isinstance(source, StepRunOutput)
    assert source.run.run_id == "consumer.producer"
    assert plan.resolved_outputs[source] == configured_output


def test_nested_configured_producers_keep_the_full_run_path(config):
    source, producer, consumer = _make_nested_configurable_steps()
    config.update(
        {
            "source": {"profile": "main"},
            "producer": {"mode": "main"},
            "steps": {
                "consumer": {
                    "inputs": {
                        "producer_result": {
                            "parameters": {"mode": "alternate"},
                        },
                    },
                },
                "producer": {
                    "inputs": {
                        "source_result": {
                            "parameters": {"profile": "nested"},
                        },
                    },
                },
            },
        }
    )

    plan = build_plan(
        [consumer],
        config,
        _registry={step.name: step for step in (source, producer, consumer)},
    )

    assert _scheduled_run_ids(plan) == [
        "consumer.producer.source",
        "consumer.producer",
        "consumer",
    ]
    source_run, producer_run, consumer_run = plan.runs_to_execute
    assert source_run.config["source"]["profile"] == "nested"
    assert producer_run.config["producer"]["mode"] == "alternate"
    assert config["source"]["profile"] == "main"
    assert config["producer"]["mode"] == "main"

    producer_source = producer_run.inputs[0].source
    consumer_source = consumer_run.inputs[0].source
    assert isinstance(producer_source, StepRunOutput)
    assert isinstance(consumer_source, StepRunOutput)
    assert producer_source.run is source_run
    assert consumer_source.run is producer_run


def test_task_listed_producer_keeps_main_and_configured_run_separate(config):
    producer, consumer = _make_configurable_producer_and_consumer()
    registered_producer = type(producer)()
    registered_consumer = type(consumer)()
    _configure_producer_modes(config, {"consumer": "alternate"})

    class FakeTask:
        name = "task"
        description = ""
        steps = [consumer, producer]

    plan = build_plan(
        [cast(Runnable, FakeTask())],
        config,
        _registry={
            registered_producer.name: registered_producer,
            registered_consumer.name: registered_consumer,
        },
    )

    assert [run.run_id for run in plan.goals] == ["consumer", "producer"]
    assert _scheduled_run_ids(plan) == [
        "producer",
        "consumer.producer",
        "consumer",
    ]
    consumer_source = plan.goals[0].inputs[0].source
    assert isinstance(consumer_source, StepRunOutput)
    assert consumer_source.run.run_id == "consumer.producer"


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
        _registry={
            step.name: step
            for step in (source, intermediate, goal)
        },
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
        _registry={
            step.name: step
            for step in (source, intermediate, goal)
        },
    )

    assert _scheduled_run_ids(plan) == ["source", "intermediate", "goal"]
    assert plan.resolved_outputs == {}
