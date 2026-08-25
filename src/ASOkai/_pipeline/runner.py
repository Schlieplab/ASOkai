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
    resolve_run_inputs,
    resolve_run_sequence_inputs,
)
from ASOkai._cwl.job_bundle import write_cwl_job_bundle
from ASOkai._cwl.executors import CwlToolExecutor, Executor, ToilExecutor
from ASOkai._pipeline.base import Runnable
from ASOkai._pipeline.contracts.execution import ExecutionPlan, StepRun
from ASOkai._pipeline.plan import build_plan
from ASOkai.Plugins._registry import get_steps, get_tasks, get_workflows
from ASOkai._pipeline.steps.base import Step
from ASOkai._pipeline.tasks.base import Task
from ASOkai._pipeline.workflows.base import Workflow

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
    runs: tuple[StepRun, ...],
) -> None:
    """Ensure the CWL publisher materialized valid planned outputs."""
    for run in runs:
        try:
            run.step.validate_output_files(dict(run.config))
        except FileNotFoundError as error:
            raise RuntimeError(
                f"CWL did not publish expected output(s) for "
                f"'{run.run_id}': {error}"
            ) from error
        except (OSError, UnicodeError, TypeError, ValueError) as error:
            raise RuntimeError(
                f"CWL published invalid output(s) for '{run.run_id}': {error}"
            ) from error


def _requested_outputs(plan: ExecutionPlan) -> dict[str, Path]:
    """Return every requested output under its run-qualified name."""
    requested: dict[str, Path] = {}
    for run in plan.goals:
        paths = run.step.validated_output_paths(dict(run.config))
        for output in run.step.spec.outputs:
            requested[run.output(output).qualified_name] = paths[output.name]
    return requested


# ---------------------------------------------------------------------------
# Dry-run reporting (same resolution logic, annotated display)
# ---------------------------------------------------------------------------

def _log_dry_run_plan(plan: ExecutionPlan, label: str) -> None:
    """
    Per-step dry-run breakdown. Uses run input resolution with plan context
    so the display reflects exactly the same priority logic as execution.
    """
    run_ids_to_execute = {run.run_id for run in plan.runs_to_execute}
    logger.info(
        "[%s] dry-run — would run %d step(s):",
        label,
        len(plan.runs_to_execute),
    )

    for run in plan.runs_to_execute:
        logger.info("  ── %s", run.run_id)
        resolved = resolve_run_inputs(
            run,
            resolved_outputs=dict(plan.resolved_outputs),
            run_ids_to_execute=run_ids_to_execute,
        )
        for cwl_key, ri in resolved.items():
            if ri.source == "dep_wired":
                assert ri.producer_output is not None
                logger.info(
                    "    %-22s wired from '%s'",
                    cwl_key,
                    ri.producer_output.qualified_name,
                )
            elif ri.source == "dep_disk":
                assert ri.producer_output is not None
                p = ri.path
                if p is not None:
                    status = "OK" if p.exists() else "MISSING"
                    logger.info(
                        "    %-22s %s  (%s)  [from '%s']",
                        cwl_key,
                        p,
                        status,
                        ri.producer_output.qualified_name,
                    )
                else:
                    logger.info(
                        "    %-22s MISSING — output '%s' unknown",
                        cwl_key,
                        ri.producer_output.qualified_name,
                    )
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
    dry_run: bool = False,
    executor: Executor | None = None,
) -> dict[str, Path] | None:
    """
    Execute an ExecutionPlan.

    A generated wrapper workflow and its generated step CommandLineTool files
    are written into a job bundle before execution.
    """

    executor = executor or CwlToolExecutor()

    if not plan.runs_to_execute:
        logger.info("[%s] all outputs already exist, nothing to run.", label)
        for run_output, path in plan.resolved_outputs.items():
            logger.info(
                "  %s/%s: %s",
                run_output.run.run_id,
                run_output.output.name,
                path,
            )
        return _requested_outputs(plan)

    cwl_bundle = generate_cwl_bundle(
        list(plan.runs_to_execute),
    )
    inputs = resolve_run_sequence_inputs(
        plan.runs_to_execute,
        dict(plan.resolved_outputs),
    )
    last_run = plan.runs_to_execute[-1]

    if dry_run:
        _log_dry_run_plan(plan, label)
        return _requested_outputs(plan)

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

    for run in plan.runs_to_execute:
        run_config = dict(run.config)
        if any(path.exists() for path in run.step.output_paths(run_config).values()):
            logger.info("[%s] replacing outputs for '%s'.", label, run.run_id)
            run.step.cleanup(run_config)

    if len(plan.runs_to_execute) == 1:
        logger.info("[%s] running '%s'.", label, last_run.run_id)
    else:
        logger.info(
            "[%s] running %d steps.",
            label,
            len(plan.runs_to_execute),
        )
    datadir = Path(config["datadir"])
    executor.run(str(job_dir / "run.cwl"), inputs, datadir)
    _validate_published_outputs(plan.runs_to_execute)
    return _requested_outputs(plan)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_all(
    runnables: list[Runnable],
    config: dict,
    *,
    force: bool = False,
    dry_run: bool = False,
    non_recursive: bool = False,
    executor: Executor | None = None,
) -> dict[str, Path] | None:
    """Run an arbitrary list of Runnables as a single unified ExecutionPlan."""
    if not runnables:
        raise ValueError("run_all called with an empty runnables list.")

    label = ", ".join(r.name for r in runnables)
    plan = build_plan(
        runnables,
        config,
        non_recursive=non_recursive,
        force=force,
    )
    return run_plan(
        plan,
        label,
        config,
        dry_run=dry_run,
        executor=executor,
    )


def export_all(
    runnables: list[Runnable],
    config: dict,
    *,
    non_recursive: bool = False,
    outdir: Path | None = None,
    runner_name: str = "cwltool",
) -> Path:
    """Export a complete runnable CWL bundle for the selected runnables."""
    if not runnables:
        raise ValueError("export_all called with an empty runnables list.")

    label = ", ".join(r.name for r in runnables)
    plan = build_plan(
        runnables,
        config,
        non_recursive=non_recursive,
        force=True,
    )
    if not plan.runs_to_execute:
        raise RuntimeError("No steps were selected for export.")

    cwl_bundle = generate_cwl_bundle(
        list(plan.runs_to_execute),
    )
    inputs = resolve_run_sequence_inputs(
        plan.runs_to_execute,
        dict(plan.resolved_outputs),
    )
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
    non_recursive: bool = False,
    executor: Executor | None = None,
) -> dict[str, Path] | None:
    """Run a single step by name."""
    steps = get_steps()
    if step_name not in steps:
        raise ValueError(f"Unknown step '{step_name}'. Run 'ASOkai list steps' to see available steps.")

    step = steps[step_name]
    if not isinstance(step, Step):
        raise TypeError(f"Step '{step_name}' does not conform to the Step protocol.")

    plan = build_plan(
        [step],
        config,
        non_recursive=non_recursive,
        force=force,
    )

    return run_plan(
        plan,
        step_name,
        config,
        dry_run=dry_run,
        executor=executor,
    )


def run_task(
    task_name: str,
    config: dict,
    *,
    force: bool = False,
    dry_run: bool = False,
    non_recursive: bool = False,
    executor: Executor | None = None,
) -> dict[str, Path] | None:
    tasks = get_tasks()
    if task_name not in tasks:
        raise ValueError(f"Unknown task '{task_name}'. Run 'ASOkai list tasks' to see available tasks.")
    task = tasks[task_name]
    if not isinstance(task, Task):
        raise TypeError(f"Task '{task_name}' does not conform to the Task protocol.")

    plan = build_plan(
        [task],
        config,
        non_recursive=non_recursive,
        force=force,
    )
    return run_plan(
        plan,
        task_name,
        config,
        dry_run=dry_run,
        executor=executor,
    )


def run_workflow(
    workflow_name: str,
    config: dict,
    *,
    force: bool = False,
    dry_run: bool = False,
    non_recursive: bool = False,
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

    plan = build_plan(
        [wf],
        config,
        non_recursive=non_recursive,
        force=force,
    )
    return run_plan(
        plan,
        workflow_name,
        config,
        dry_run=dry_run,
        executor=executor,
    )
