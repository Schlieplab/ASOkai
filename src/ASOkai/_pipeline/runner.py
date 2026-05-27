"""
Filename: src/pipeline/runner.py
Description: Executes planned pipeline steps with optional dry-run and CWL export.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

import logging
from pathlib import Path

from ASOkai._cwl.generation import generate_cwl
from ASOkai._cwl.input_resolution import (
    resolve_step_inputs,
    resolve_step_sequence_inputs,
)
from ASOkai._cwl.export import write_cwl_job_bundle
from ASOkai._cwl.executors import CwlToolExecutor, Executor
from ASOkai._pipeline.base import Runnable, Step, Task, Workflow
from ASOkai._pipeline.plan import ExecutionPlan, build_plan
from ASOkai._pipeline.registry import get_steps, get_tasks, get_workflows

logger = logging.getLogger(__name__)


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
            elif ri.source == "output_path":
                logger.info("    %-22s %s  [→ output]", cwl_key, ri.cwl_value)
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
    export_cwl: Path | None = None,
    export_only: Path | None = None,
    executor: Executor | None = None,
) -> dict[str, Path] | None:
    """
    Execute an ExecutionPlan.

    Single-step fast path:
      resolve inputs, then run the step's static CWL directly.

    Multi-step path:
      generate a workflow CWL document, then run it as one executor job.
    """
    
    executor = executor or CwlToolExecutor()

    if not plan.steps_to_run:
        logger.info("[%s] all outputs already exist, nothing to run.", label)
        for key, path in plan.pre_resolved.items():
            logger.info("  %s: %s", key, path)
        return dict(plan.pre_resolved)

    cwl_doc = generate_cwl(plan.steps_to_run, plan.pre_resolved, config)
    inputs = resolve_step_sequence_inputs(plan.steps_to_run, config, plan.pre_resolved)
    last_step = plan.steps_to_run[-1]
    outdir = last_step.outdir(config)

    if export_cwl:
        export_cwl.parent.mkdir(parents=True, exist_ok=True)
        export_cwl.write_text(cwl_doc)
        logger.info("[%s] CWL exported to %s", label, export_cwl)
        return None

    if dry_run and export_only is None:
        _log_dry_run_plan(plan, config, label)
        return last_step.output_paths(config)

    job_parent = export_only or Path(config["datadir"]) / "jobs"
    job_dir = write_cwl_job_bundle(
        cwl_doc=cwl_doc,
        inputs=inputs,
        parent_dir=job_parent,
        label=label,
        runner_name=executor.runner_name,
        name_prefix="asokai-export" if export_only is not None else "asokai-job",
    )
    logger.info("[%s] CWL job bundle written to %s", label, job_dir)

    if export_only is not None:
        return None

    if len(plan.steps_to_run) == 1:
        step = plan.steps_to_run[0]

        if force and not dry_run:
            logger.info("[%s] force=True, cleaning up '%s'.", label, step.name)
            step.cleanup(config)

        logger.info("[%s] running '%s'.", label, step.name)
        executor.run(str(job_dir / "workflow.cwl"), inputs, outdir)
        return step.output_paths(config)

    # Multi-step path
    if force and not dry_run:
        for step in plan.steps_to_run:
            step.cleanup(config)

    logger.info("[%s] running %d steps.", label, len(plan.steps_to_run))
    executor.run(str(job_dir / "workflow.cwl"), inputs, outdir)
    return last_step.output_paths(config)


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
    export_cwl: Path | None = None,
    export_only: Path | None = None,
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
        export_cwl=export_cwl,
        export_only=export_only,
        executor=executor,
    )


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
        outputs = step.output_paths(config)
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
    export_cwl: Path | None = None,
    export_only: Path | None = None,
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
        export_cwl=export_cwl,
        export_only=export_only,
        executor=executor,
    )


def run_workflow(
    workflow_name: str,
    config: dict,
    *,
    force: bool = False,
    dry_run: bool = False,
    recursive: bool = False,
    export_cwl: Path | None = None,
    export_only: Path | None = None,
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
        export_cwl=export_cwl,
        export_only=export_only,
        executor=executor,
    )
