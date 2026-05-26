"""Tests for pipeline.plan.build_plan."""
from __future__ import annotations

import pytest
from pathlib import Path
from typing import cast

from pipeline.base import Runnable, Step
from pipeline.plan import build_plan


# ---------------------------------------------------------------------------
# Minimal step factory
# ---------------------------------------------------------------------------

def _make_step(
    name: str,
    deps: list[str] | None = None,
    *,
    exists: bool = False,
    output_names: list[str] | None = None,
) -> Step:
    """Return a minimal object that satisfies the Step protocol."""
    if output_names is None:
        output_names = [f"{name}_out"]
    dependencies = list(deps or [])

    class _Step:
        name: str
        description: str
        cli_module: str
        dependencies: list[str]
        config_map: dict[str, str]
        input_overrides: dict[str, str]

        def __init__(self) -> None:
            self.name = name
            self.description = ""
            self.cli_module = "tests.fake_step"
            self.dependencies = dependencies
            self.config_map = {}
            self.input_overrides = {}

        @property
        def cwl_path(self) -> str:
            return f"/fake/{name}.cwl"

        def outdir(self, config: dict) -> Path:
            return Path(config.get("datadir", "/tmp")) / name

        def output_paths(self, config: dict) -> dict[str, Path]:
            base = self.outdir(config)
            return {k: base / f"{k}.txt" for k in output_names}

        def outputs_exist(self, _config: dict) -> bool:
            return exists

        def cleanup(self, _config: dict) -> None:
            pass

    return _Step()


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
    assert "result" in plan.pre_resolved


def test_force_keeps_done_step_in_steps_to_run(cfg):
    step = _make_step("alpha", exists=True)
    plan = build_plan([step], cfg, force=True)
    assert [s.name for s in plan.steps_to_run] == ["alpha"]
    assert plan.pre_resolved == {}


def test_dep_done_goes_to_pre_resolved(cfg):
    dep = _make_step("dep", exists=True, output_names=["dep_out"])
    step = _make_step("step", deps=["dep"])
    plan = build_plan([step, dep], cfg)
    assert [s.name for s in plan.steps_to_run] == ["step"]
    assert "dep_out" in plan.pre_resolved


def test_dep_not_done_included_in_steps_to_run(cfg):
    dep = _make_step("dep")
    step = _make_step("step", deps=["dep"])
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
    step = _make_step("step", deps=["dep"])
    plan = build_plan([step, dep], cfg)
    names = [s.name for s in plan.steps_to_run]
    assert names.index("dep") < names.index("step")


def test_topo_order_chain(cfg):
    a = _make_step("a")
    b = _make_step("b", deps=["a"])
    c = _make_step("c", deps=["b"])
    plan = build_plan([c, a, b], cfg)
    names = [s.name for s in plan.steps_to_run]
    assert names == ["a", "b", "c"]


def test_cycle_raises(cfg):
    a = _make_step("a", deps=["b"])
    b = _make_step("b", deps=["a"])
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


# ---------------------------------------------------------------------------
# Recursive dependency resolution
# ---------------------------------------------------------------------------

def test_recursive_prepends_missing_dep(cfg):
    dep = _make_step("dep")
    step = _make_step("step", deps=["dep"])
    registry = {"dep": dep, "step": step}
    plan = build_plan([step], cfg, recursive=True, _registry=registry)
    names = [s.name for s in plan.steps_to_run]
    assert "dep" in names
    assert names.index("dep") < names.index("step")


def test_recursive_skips_done_dep(cfg):
    dep = _make_step("dep", exists=True, output_names=["dep_out"])
    step = _make_step("step", deps=["dep"])
    registry = {"dep": dep, "step": step}
    plan = build_plan([step], cfg, recursive=True, _registry=registry)
    names = [s.name for s in plan.steps_to_run]
    assert "dep" not in names
    assert "dep_out" in plan.pre_resolved


def test_recursive_unknown_dep_raises(cfg):
    step = _make_step("step", deps=["ghost"])
    registry = {"step": step}
    with pytest.raises(ValueError, match="unknown step 'ghost'"):
        build_plan([step], cfg, recursive=True, _registry=registry)


def test_nonrecursive_external_done_dep_goes_to_pre_resolved(cfg):
    dep = _make_step("dep", exists=True, output_names=["dep_out"])
    step = _make_step("step", deps=["dep"])
    registry = {"dep": dep, "step": step}
    plan = build_plan([step], cfg, recursive=False, _registry=registry)
    assert [s.name for s in plan.steps_to_run] == ["step"]
    assert "dep_out" in plan.pre_resolved


def test_force_keeps_external_done_dep_pre_resolved(cfg):
    dep = _make_step("dep", exists=True, output_names=["dep_out"])
    step = _make_step("step", deps=["dep"])
    registry = {"dep": dep, "step": step}
    plan = build_plan([step], cfg, force=True, _registry=registry)
    assert [s.name for s in plan.steps_to_run] == ["step"]
    assert "dep_out" in plan.pre_resolved


def test_nonrecursive_external_missing_dep_raises(cfg):
    dep = _make_step("dep", exists=False)
    step = _make_step("step", deps=["dep"])
    registry = {"dep": dep, "step": step}
    with pytest.raises(RuntimeError, match="use --recursive"):
        build_plan([step], cfg, recursive=False, _registry=registry)


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
