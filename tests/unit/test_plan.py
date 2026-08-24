#!/usr/bin/env python
"""
Filename: tests/unit/test_plan.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Version: 0.1.1
Description: Tests for goal-driven pipeline planning.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

from typing import cast

import pytest

from ASOkai.Plugins import FileInput, FileOutput, Runnable, Step, StepSpec
from ASOkai._pipeline.plan import StepRunOutput, build_plan


def _make_step(
    name: str,
    dependencies: list[Step] | None = None,
    *,
    outputs_valid: bool = False,
    output_names: list[str] | None = None,
    input_override: str | None = None,
    compatible_with: dict[str, list[str]] | None = None,
) -> Step:
    """Return a minimal concrete step for planner tests."""
    outputs = [
        FileOutput(
            output_name,
            destination=f"{name}/{output_name}.txt",
        )
        for output_name in output_names or [f"{name}_out"]
    ]
    spec = StepSpec(
        inputs=[
            FileInput(
                dependency.spec.outputs[0].name,
                source=dependency.spec.outputs[0],
                override=input_override,
            )
            for dependency in dependencies or []
        ],
        outputs=outputs,
        compatible_with=compatible_with or {},
    )

    def validate_output_files(self: Step, config: dict):
        if not outputs_valid:
            raise FileNotFoundError
        return self.validated_output_paths(config)

    step_type = type(
        f"_{name.replace('-', '_').title()}Step",
        (Step,),
        {
            "name": name,
            "description": "",
            "spec": spec,
            "validate_output_files": validate_output_files,
            **{f"{output.name}_output": output for output in outputs},
        },
    )
    return step_type()


@pytest.fixture
def config(tmp_path):
    return {"datadir": str(tmp_path)}


def _scheduled_names(plan) -> list[str]:
    return [run.name for run in plan.runs_to_execute]


def test_missing_goal_is_scheduled(config):
    step = _make_step("alpha")

    plan = build_plan([step], config, _registry={step.name: step})

    assert _scheduled_names(plan) == ["alpha"]
    assert [run.name for run in plan.goals] == ["alpha"]
    assert plan.resolved_outputs == {}


def test_valid_goal_output_is_reused(config):
    step = _make_step(
        "alpha",
        outputs_valid=True,
        output_names=["result"],
    )

    plan = build_plan([step], config, _registry={step.name: step})

    assert plan.runs_to_execute == ()
    assert {
        (run_output.run.name, run_output.output.name)
        for run_output in plan.resolved_outputs
    } == {("alpha", "result")}


def test_force_schedules_valid_goal(config):
    step = _make_step("alpha", outputs_valid=True)

    plan = build_plan(
        [step],
        config,
        force=True,
        _registry={step.name: step},
    )

    assert _scheduled_names(plan) == ["alpha"]
    assert plan.resolved_outputs == {}


@pytest.mark.parametrize("outputs_valid", [False, True])
def test_incompatible_goal_is_rejected_before_reuse(config, outputs_valid):
    step = _make_step(
        "restricted",
        outputs_valid=outputs_valid,
        compatible_with={"analysis.mode": ["supported"]},
    )
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

    assert _scheduled_names(plan) == ["dependency", "goal"]
    binding = plan.goals[0].inputs[0]
    assert isinstance(binding.source, StepRunOutput)
    assert binding.source.run.name == "dependency"


def test_valid_dependency_is_reused(config):
    dependency = _make_step(
        "dependency",
        outputs_valid=True,
        output_names=["result"],
    )
    goal = _make_step("goal", [dependency])

    plan = build_plan(
        [goal],
        config,
        _registry={dependency.name: dependency, goal.name: goal},
    )

    assert _scheduled_names(plan) == ["goal"]
    reused_output = plan.goals[0].inputs[0].source
    assert isinstance(reused_output, StepRunOutput)
    assert plan.resolved_outputs[reused_output].name == "result.txt"


def test_dependency_chain_is_scheduled_in_topological_order(config):
    first = _make_step("first")
    second = _make_step("second", [first])
    goal = _make_step("goal", [second])

    plan = build_plan(
        [goal],
        config,
        _registry={step.name: step for step in (first, second, goal)},
    )

    assert _scheduled_names(plan) == ["first", "second", "goal"]


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

    assert _scheduled_names(plan) == ["shared", "first", "second"]
    assert [run.name for run in plan.goals] == ["first", "second"]


def test_equal_port_names_from_different_runs_do_not_collide(config):
    first = _make_step("first", outputs_valid=True, output_names=["result"])
    second = _make_step("second", outputs_valid=True, output_names=["result"])

    plan = build_plan(
        [first, second],
        config,
        _registry={first.name: first, second.name: second},
    )

    assert len(plan.resolved_outputs) == 2
    assert {output.run.name for output in plan.resolved_outputs} == {
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
    dependency = _make_step("dependency", outputs_valid=True)
    goal = _make_step("goal", [dependency])

    plan = build_plan(
        [goal],
        config,
        non_recursive=True,
        _registry={dependency.name: dependency, goal.name: goal},
    )

    assert _scheduled_names(plan) == ["goal"]


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

    assert _scheduled_names(plan) == ["dependency", "goal"]


def test_force_does_not_force_valid_dependency(config):
    dependency = _make_step("dependency", outputs_valid=True)
    goal = _make_step("goal")
    goal_with_dependency = _make_step("goal", [dependency])

    plan = build_plan(
        [goal_with_dependency],
        config,
        force=True,
        _registry={dependency.name: dependency, goal.name: goal_with_dependency},
    )

    assert _scheduled_names(plan) == ["goal"]


def test_file_override_bypasses_dependency(config, tmp_path):
    dependency = _make_step("dependency")
    goal = _make_step(
        "goal",
        [dependency],
        input_override="inputs.dependency",
    )
    override = tmp_path / "override.txt"
    override.touch()
    config["inputs"] = {"dependency": str(override)}

    plan = build_plan(
        [goal],
        config,
        non_recursive=True,
        _registry={dependency.name: dependency, goal.name: goal},
    )

    assert _scheduled_names(plan) == ["goal"]
    assert plan.goals[0].inputs[0].source == override.resolve()


def test_task_members_are_terminal_goals(config):
    dependency = _make_step("dependency")
    goal = _make_step("goal", [dependency])

    class FakeTask:
        name = "task"
        description = ""
        steps = [goal]

    plan = build_plan(
        [cast(Runnable, FakeTask())],
        config,
        _registry={dependency.name: dependency, goal.name: goal},
    )

    assert [run.name for run in plan.goals] == ["goal"]
    assert _scheduled_names(plan) == ["dependency", "goal"]


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

    assert [run.name for run in plan.goals] == ["first", "second"]
    assert _scheduled_names(plan) == ["shared", "first", "second"]
