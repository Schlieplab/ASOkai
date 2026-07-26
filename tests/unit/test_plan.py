#!/usr/bin/env python
"""
Filename: tests/unit/test_plan.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Version: 0.1.1
Description: Tests for pipeline.plan.build_plan.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

import pytest
from typing import cast

from ASOkai.plugin_api import (
    FileInput,
    FileOutput,
    Runnable,
    Step,
    StepSpec,
)
from ASOkai._pipeline.plan import build_plan


# ---------------------------------------------------------------------------
# Minimal step factory
# ---------------------------------------------------------------------------

def _make_step(
    name: str,
    deps: list[Step] | None = None,
    *,
    exists: bool = False,
    output_names: list[str] | None = None,
    input_override: str | None = None,
) -> Step:
    """Return a minimal concrete Step for plan tests."""
    if output_names is None:
        output_names = [f"{name}_out"]
    outputs = [
        FileOutput(
            key,
            destination=f"{name}/{key}.txt",
        )
        for key in output_names
    ]
    spec = StepSpec(
        inputs=[
            FileInput(
                dep.spec.outputs[0].name,
                source=dep.spec.outputs[0],
                override=input_override,
            )
            for dep in deps or []
        ],
        outputs=outputs,
    )

    def outputs_exist(self, config: dict) -> bool:
        return exists

    def cleanup(self, config: dict) -> None:
        pass

    step_type = type(
        "_Step",
        (Step,),
        {
            "name": name,
            "description": "",
            "spec": spec,
            "outputs_exist": outputs_exist,
            "cleanup": cleanup,
            **{f"{output.name}_output": output for output in outputs},
        },
    )
    return step_type()


@pytest.fixture
def cfg(tmp_path):
    return {"datadir": str(tmp_path)}


# ---------------------------------------------------------------------------
# Basic flattening and plan construction
# ---------------------------------------------------------------------------

def test_single_step_no_deps_all_in_steps_to_run(cfg):
    step = _make_step("alpha")
    plan = build_plan([step], cfg)
    assert [s.name for s in plan.steps_to_run] == ["alpha"]
    assert plan.pre_resolved == {}


def test_single_step_outputs_exist_goes_to_pre_resolved(cfg):
    step = _make_step("alpha", exists=True, output_names=["result"])
    plan = build_plan([step], cfg)
    assert plan.steps_to_run == []
    assert step.spec.output("result") in plan.pre_resolved


def test_force_keeps_done_step_in_steps_to_run(cfg):
    step = _make_step("alpha", exists=True)
    plan = build_plan([step], cfg, force=True)
    assert [s.name for s in plan.steps_to_run] == ["alpha"]
    assert plan.pre_resolved == {}


def test_dep_done_goes_to_pre_resolved(cfg):
    dep = _make_step("dep", exists=True, output_names=["dep_out"])
    step = _make_step("step", deps=[dep])
    plan = build_plan([step, dep], cfg)
    assert [s.name for s in plan.steps_to_run] == ["step"]
    assert dep.spec.output("dep_out") in plan.pre_resolved


def test_dep_not_done_included_in_steps_to_run(cfg):
    dep = _make_step("dep")
    step = _make_step("step", deps=[dep])
    plan = build_plan([dep, step], cfg)
    names = [s.name for s in plan.steps_to_run]
    assert names == ["dep", "step"]
    assert plan.pre_resolved == {}


# ---------------------------------------------------------------------------
# Topological ordering
# ---------------------------------------------------------------------------

def test_topo_order_dep_first(cfg):
    """dep must come before step regardless of input order."""
    dep = _make_step("dep")
    step = _make_step("step", deps=[dep])
    plan = build_plan([step, dep], cfg)
    names = [s.name for s in plan.steps_to_run]
    assert names.index("dep") < names.index("step")


def test_topo_order_chain(cfg):
    a = _make_step("a")
    b = _make_step("b", deps=[a])
    c = _make_step("c", deps=[b])
    plan = build_plan([c, a, b], cfg)
    names = [s.name for s in plan.steps_to_run]
    assert names == ["a", "b", "c"]


def test_cycle_raises(cfg):
    a = _make_step("a")
    b = _make_step("b", deps=[a])
    type(a).spec = StepSpec(
        inputs=[
            FileInput(
                "b_out",
                source=b.spec.output("b_out"),
            )
        ],
        outputs=a.spec.outputs,
    )
    with pytest.raises(ValueError, match="cycle"):
        build_plan([a, b], cfg)


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

def test_duplicate_steps_deduplicated(cfg):
    step = _make_step("alpha")
    plan = build_plan([step, step], cfg)
    assert len(plan.steps_to_run) == 1


def test_duplicate_across_runnables_deduplicated(cfg):
    """Same step included from two different runnables appears only once."""
    shared = _make_step("shared")
    plan = build_plan([shared, shared], cfg)
    assert sum(1 for s in plan.steps_to_run if s.name == "shared") == 1


def test_pre_resolved_outputs_are_keyed_by_producer_and_port(cfg):
    first = _make_step("first", exists=True, output_names=["result"])
    second = _make_step("second", exists=True, output_names=["result"])

    plan = build_plan([first, second], cfg)

    assert set(plan.pre_resolved) == {
        first.spec.output("result"),
        second.spec.output("result"),
    }


def test_unknown_referenced_output_raises(cfg):
    producer = _make_step("producer", output_names=["actual"])
    shadow_producer = _make_step("producer", output_names=["missing"])
    consumer = _make_step("consumer", deps=[shadow_producer])

    with pytest.raises(ValueError, match="unknown output 'missing'"):
        build_plan([producer, consumer], cfg)


# ---------------------------------------------------------------------------
# Recursive dependency resolution
# ---------------------------------------------------------------------------

def test_recursive_prepends_missing_dep(cfg):
    dep = _make_step("dep")
    step = _make_step("step", deps=[dep])
    registry = {"dep": dep, "step": step}
    plan = build_plan([step], cfg, recursive=True, _registry=registry)
    names = [s.name for s in plan.steps_to_run]
    assert "dep" in names
    assert names.index("dep") < names.index("step")


def test_recursive_skips_done_dep(cfg):
    dep = _make_step("dep", exists=True, output_names=["dep_out"])
    step = _make_step("step", deps=[dep])
    registry = {"dep": dep, "step": step}
    plan = build_plan([step], cfg, recursive=True, _registry=registry)
    names = [s.name for s in plan.steps_to_run]
    assert "dep" not in names
    assert dep.spec.output("dep_out") in plan.pre_resolved


def test_recursive_unknown_dep_raises(cfg):
    ghost = _make_step("ghost")
    step = _make_step("step", deps=[ghost])
    registry = {"step": step}
    with pytest.raises(ValueError, match="unknown step 'ghost'"):
        build_plan([step], cfg, recursive=True, _registry=registry)


def test_nonrecursive_external_done_dep_goes_to_pre_resolved(cfg):
    dep = _make_step("dep", exists=True, output_names=["dep_out"])
    step = _make_step("step", deps=[dep])
    registry = {"dep": dep, "step": step}
    plan = build_plan([step], cfg, recursive=False, _registry=registry)
    assert [s.name for s in plan.steps_to_run] == ["step"]
    assert dep.spec.output("dep_out") in plan.pre_resolved


def test_force_keeps_external_done_dep_pre_resolved(cfg):
    dep = _make_step("dep", exists=True, output_names=["dep_out"])
    step = _make_step("step", deps=[dep])
    registry = {"dep": dep, "step": step}
    plan = build_plan([step], cfg, force=True, _registry=registry)
    assert [s.name for s in plan.steps_to_run] == ["step"]
    assert dep.spec.output("dep_out") in plan.pre_resolved


def test_nonrecursive_external_missing_dep_raises(cfg):
    dep = _make_step("dep", exists=False)
    step = _make_step("step", deps=[dep])
    registry = {"dep": dep, "step": step}
    with pytest.raises(RuntimeError, match="use --recursive"):
        build_plan([step], cfg, recursive=False, _registry=registry)


def test_nonrecursive_override_replaces_external_dependency(cfg, tmp_path):
    dep = _make_step("dep", exists=False, output_names=["dep_out"])
    step = _make_step(
        "step",
        deps=[dep],
        input_override="inputs.dep",
    )
    registry = {"dep": dep, "step": step}
    cfg["inputs"] = {"dep": str(tmp_path / "override.txt")}

    plan = build_plan([step], cfg, recursive=False, _registry=registry)

    assert [planned.name for planned in plan.steps_to_run] == ["step"]
    assert plan.pre_resolved == {}


def test_recursive_override_does_not_schedule_dependency(cfg, tmp_path):
    dep = _make_step("dep", exists=False, output_names=["dep_out"])
    step = _make_step(
        "step",
        deps=[dep],
        input_override="inputs.dep",
    )
    registry = {"dep": dep, "step": step}
    cfg["inputs"] = {"dep": str(tmp_path / "override.txt")}

    plan = build_plan([step], cfg, recursive=True, _registry=registry)

    assert [planned.name for planned in plan.steps_to_run] == ["step"]
    assert plan.pre_resolved == {}


# ---------------------------------------------------------------------------
# Mixed runnables (Task and Workflow-like objects)
# ---------------------------------------------------------------------------

def test_task_flattened_to_steps(cfg):
    s1 = _make_step("s1")
    s2 = _make_step("s2")

    class FakeTask:
        name = "task"
        description = ""
        steps = [s1, s2]

        def output_paths(self, c): return {}
        def outputs_exist(self, c): return False
        def cleanup(self, c): pass

    plan = build_plan([cast(Runnable, FakeTask())], cfg)
    names = [s.name for s in plan.steps_to_run]
    assert names == ["s1", "s2"]


def test_workflow_flattened_to_steps(cfg):
    s1 = _make_step("s1")
    s2 = _make_step("s2")

    class FakeWorkflow:
        name = "wf"
        description = ""
        members = [s1, s2]

        def output_paths(self, c): return {}
        def outputs_exist(self, c): return False
        def cleanup(self, c): pass

    plan = build_plan([cast(Runnable, FakeWorkflow())], cfg)
    names = [s.name for s in plan.steps_to_run]
    assert names == ["s1", "s2"]


def test_mixed_step_and_task_deduplicated(cfg):
    shared = _make_step("shared")

    class FakeTask:
        name = "task"
        description = ""
        steps = [shared]

        def output_paths(self, c): return {}
        def outputs_exist(self, c): return False
        def cleanup(self, c): pass

    plan = build_plan([shared, cast(Runnable, FakeTask())], cfg)
    assert sum(1 for s in plan.steps_to_run if s.name == "shared") == 1
