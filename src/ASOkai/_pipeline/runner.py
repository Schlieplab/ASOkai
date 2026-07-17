#!/usr/bin/env python
"""
Filename: src/ASOkai/_pipeline/runner.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Version: 0.1.1
Description: Executes planned pipeline steps and exports runnable CWL bundles.
License: LGPL-3.0-or-later
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ASOkai._cwl.generation import generate_cwl_bundle
from ASOkai._cwl.input_resolution import (
    resolve_step_inputs,
    resolve_step_sequence_inputs,
)
from ASOkai._cwl.export import write_cwl_job_bundle
from ASOkai._cwl.executors import CwlToolExecutor, Executor, ToilExecutor
from ASOkai._pipeline.base import Runnable, Step, Task, Workflow
from ASOkai._pipeline.plan import ExecutionPlan, build_plan
from ASOkai._pipeline.registry import get_steps, get_tasks, get_workflows

logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class RunnerConfig:
    """Configuration shared by the CLI, exporter, and execution path."""

    executable: str
    executor_factory: Callable[[], Executor]

    def create_executor(self) -> Executor:
        return self.executor_factory()


RUNNERS = {
    "toil": RunnerConfig("toil-cwl-runner", ToilExecutor),
    "cwltool": RunnerConfig("cwltool", CwlToolExecutor),
}
RUNNER_NAMES = tuple(RUNNERS)


def runner_config_from_name(name: str) -> RunnerConfig:
    """Return runner configuration for a public CLI name."""
    try:
        return RUNNERS[name]
    except KeyError as exc:
        choices = ", ".join(RUNNER_NAMES)
        raise ValueError(f"Unknown runner '{name}'. Choose one of: {choices}.") from exc


def executor_from_name(name: str) -> Executor:
    """Create the execution backend configured for a CLI runner name."""
    return runner_config_from_name(name).create_executor()


def runner_name_from_name(name: str) -> str:
    """Return the executable name configured for a public CLI runner name."""
    return runner_config_from_name(name).executable


def _validate_published_outputs(
    steps: list[Step],
    config: dict,
) -> None:
    """Ensure the CWL publisher materialized every planned output."""
    missing: list[tuple[str, Path]] = []
    for step in steps:
        for name, path in step.validated_output_paths(config).items():
            if not path.exists():
                missing.append((f"{step.name}/{name}", path))
    if missing:
        details = ", ".join(f"{name} at {path}" for name, path in missing)
        raise RuntimeError(f"CWL did not publish expected output(s): {details}.")


# ---------------------------------------------------------------------------
# Dry-run reporting (same resolution logic, annotated display)
# ---------------------------------------------------------------------------

def _log_dry_run_plan(plan: ExecutionPlan, config: dict, label: str) -> None:
    """
    Per-step dry-run breakdown.  Uses _resolve_step_inputs with plan context
    so the display reflects exactly the same priority logic as execution.
    """
    steps_in_plan = {s.name for s in plan.steps_to_run}
    logger.info("[%s] dry-run — would run %d step(s):", label, len(plan.steps_to_run))

    for step in plan.steps_to_run:
        logger.info("  ── %s", step.name)
        resolved = resolve_step_inputs(
            step, config,
            pre_resolved=plan.pre_resolved,
            steps_in_plan=steps_in_plan,
        )
        for cwl_key, ri in resolved.items():
            if ri.source == "dep_wired":
                logger.info("    %-22s wired from '%s'", cwl_key, ri.dep_name)
            elif ri.source == "dep_disk":
                p = ri.path
                if p is not None:
                    status = "OK" if p.exists() else "MISSING"
                    logger.info("    %-22s %s  (%s)", cwl_key, p, status)
                else:
                    logger.info("    %-22s MISSING — dep '%s' output unknown",
                                cwl_key, ri.dep_name)
            elif ri.source == "input_override":
                p = ri.path
                status = "OK" if p is not None and p.exists() else "MISSING"
                logger.info("    %-22s %s  (%s)  [override --config %s]",
                            cwl_key, p, status, ri.config_path)
            else:  # scalar
                logger.info("    %-22s %s", cwl_key, ri.cwl_value)


# ---------------------------------------------------------------------------
# Plan execution
# ---------------------------------------------------------------------------

def run_plan(
    plan: ExecutionPlan,
    label: str,
    config: dict,
    *,
    force: bool = False,
    dry_run: bool = False,
    executor: Executor | None = None,
) -> dict[str, Path] | None:
    """
    Execute an ExecutionPlan.

    A generated wrapper workflow and its generated step CommandLineTool files
    are written into a job bundle before execution.
    """

    executor = executor or CwlToolExecutor()

    if not plan.steps_to_run:
        logger.info("[%s] all outputs already exist, nothing to run.", label)
        for key, path in plan.pre_resolved.items():
            logger.info("  %s: %s", key, path)
        return dict(plan.pre_resolved)

    cwl_bundle = generate_cwl_bundle(
        plan.steps_to_run,
        plan.pre_resolved,
        config,
    )
    inputs = resolve_step_sequence_inputs(plan.steps_to_run, config, plan.pre_resolved)
    last_step = plan.steps_to_run[-1]

    if dry_run:
        _log_dry_run_plan(plan, config, label)
        return last_step.validated_output_paths(config)

    job_parent = Path(config["datadir"]) / "jobs"
    job_dir = write_cwl_job_bundle(
        bundle=cwl_bundle,
        inputs=inputs,
        parent_dir=job_parent,
        label=label,
        runner_name=executor.runner_name,
        name_prefix="asokai-job",
    )
    logger.info("[%s] CWL job bundle written to %s", label, job_dir)

    if force:
        for step in plan.steps_to_run:
            logger.info("[%s] force=True, cleaning up '%s'.", label, step.name)
            step.cleanup(config)

    if len(plan.steps_to_run) == 1:
        logger.info("[%s] running '%s'.", label, last_step.name)
    else:
        logger.info("[%s] running %d steps.", label, len(plan.steps_to_run))
    datadir = Path(config["datadir"])
    executor.run(str(job_dir / "run.cwl"), inputs, datadir)
    _validate_published_outputs(plan.steps_to_run, config)
    return last_step.validated_output_paths(config)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_all(
    runnables: list[Runnable],
    config: dict,
    *,
    force: bool = False,
    dry_run: bool = False,
    recursive: bool = False,
    executor: Executor | None = None,
) -> dict[str, Path] | None:
    """Run an arbitrary list of Runnables as a single unified ExecutionPlan."""
    if not runnables:
        raise ValueError("run_all called with an empty runnables list.")

    label = ", ".join(r.name for r in runnables)
    plan = build_plan(runnables, config, recursive=recursive, force=force)
    return run_plan(
        plan,
        label,
        config,
        force=force,
        dry_run=dry_run,
        executor=executor,
    )


def export_all(
    runnables: list[Runnable],
    config: dict,
    *,
    recursive: bool = False,
    outdir: Path | None = None,
    runner_name: str = "cwltool",
) -> Path:
    """Export a complete runnable CWL bundle for the selected runnables."""
    if not runnables:
        raise ValueError("export_all called with an empty runnables list.")

    label = ", ".join(r.name for r in runnables)
    plan = build_plan(runnables, config, recursive=recursive, force=True)
    if not plan.steps_to_run:
        raise RuntimeError("No steps were selected for export.")

    cwl_bundle = generate_cwl_bundle(
        plan.steps_to_run,
        plan.pre_resolved,
        config,
    )
    inputs = resolve_step_sequence_inputs(plan.steps_to_run, config, plan.pre_resolved)
    parent_dir = outdir or Path(config["datadir"]) / "jobs"
    job_dir = write_cwl_job_bundle(
        bundle=cwl_bundle,
        inputs=inputs,
        parent_dir=parent_dir,
        label=label,
        runner_name=runner_name,
        name_prefix="asokai-export",
    )
    logger.info("[%s] CWL export bundle written to %s", label, job_dir)
    return job_dir


def run_step(
    step_name: str,
    config: dict,
    *,
    force: bool = False,
    dry_run: bool = False,
    recursive: bool = False,
    executor: Executor | None = None,
) -> dict[str, Path] | None:
    """Run a single step by name."""
    steps = get_steps()
    if step_name not in steps:
        raise ValueError(f"Unknown step '{step_name}'. Run 'ASOkai list steps' to see available steps.")

    step = steps[step_name]
    if not isinstance(step, Step):
        raise TypeError(f"Step '{step_name}' does not conform to the Step protocol.")

    plan = build_plan([step], config, recursive=recursive, force=force)

    if not plan.steps_to_run and not force:
        outputs = step.validated_output_paths(config)
        logger.info("[%s] outputs exist, skipping.", step_name)
        for name, path in outputs.items():
            logger.info("  %s: %s", name, path)
        return outputs

    return run_plan(
        plan,
        step_name,
        config,
        force=force,
        dry_run=dry_run,
        executor=executor,
    )


def run_task(
    task_name: str,
    config: dict,
    *,
    force: bool = False,
    dry_run: bool = False,
    recursive: bool = False,
    executor: Executor | None = None,
) -> dict[str, Path] | None:
    tasks = get_tasks()
    if task_name not in tasks:
        raise ValueError(f"Unknown task '{task_name}'. Run 'ASOkai list tasks' to see available tasks.")
    task = tasks[task_name]
    if not isinstance(task, Task):
        raise TypeError(f"Task '{task_name}' does not conform to the Task protocol.")

    plan = build_plan([task], config, recursive=recursive, force=force)
    return run_plan(
        plan,
        task_name,
        config,
        force=force,
        dry_run=dry_run,
        executor=executor,
    )


def run_workflow(
    workflow_name: str,
    config: dict,
    *,
    force: bool = False,
    dry_run: bool = False,
    recursive: bool = False,
    executor: Executor | None = None,
) -> dict[str, Path] | None:
    workflows = get_workflows()
    if workflow_name not in workflows:
        raise ValueError(
            f"Unknown workflow '{workflow_name}'. Run 'ASOkai list workflows' to see available workflows."
        )
    wf = workflows[workflow_name]
    if not isinstance(wf, Workflow):
        raise TypeError(f"Workflow '{workflow_name}' does not conform to the Workflow protocol.")

    plan = build_plan([wf], config, recursive=recursive, force=force)
    return run_plan(
        plan,
        workflow_name,
        config,
        force=force,
        dry_run=dry_run,
        executor=executor,
    )
