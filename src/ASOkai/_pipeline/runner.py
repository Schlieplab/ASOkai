#!/usr/bin/env python
"""
Filename: src/ASOkai/_pipeline/runner.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Executes planned pipeline steps and exports runnable CWL bundles.
License: LGPL-3.0-or-later
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ASOkai._logging import prefix_log_lines
from ASOkai._cwl.generation import generate_cwl_bundle
from ASOkai._cwl.input_resolution import (
    resolve_run_inputs,
    resolve_run_sequence_inputs,
)
from ASOkai._cwl.job_bundle import write_cwl_job_bundle
from ASOkai._cwl.executors import CwlToolExecutor, Executor, ToilExecutor
from ASOkai._pipeline import config as cfg
from ASOkai._pipeline.base import Runnable
from ASOkai._pipeline.contracts.execution import ExecutionPlan, StepRun
from ASOkai._pipeline.output_receipts import record_validated_outputs
from ASOkai._pipeline.plan import build_export_plan, build_plan
from ASOkai._pipeline.steps.base import Step
from ASOkai._pipeline.tasks.base import Task
from ASOkai._pipeline.workflows.base import Workflow

logger = logging.getLogger(__name__)


def _runnable_log_context(runnable: Runnable) -> str:
    """Return the typed user-facing context for one selected runnable."""
    if isinstance(runnable, Workflow):
        kind = "workflow"
    elif isinstance(runnable, Task):
        kind = "task"
    elif isinstance(runnable, Step):
        kind = "step"
    else:
        raise TypeError(f"Unsupported runnable type: {type(runnable).__name__!r}.")
    return f"{kind}:{runnable.name}"


def _log_info(contexts: tuple[str, ...], message: str) -> None:
    """Log a user-facing message with every non-empty line contextualized."""
    logger.info("%s", prefix_log_lines(contexts, message))


@dataclass(frozen=True)
class RunnerConfig:
    """Configuration shared by the CLI, exporter, and execution path."""

    executable: str
    executor_factory: Callable[..., Executor]

    def create_executor(self, *, verbose: bool = False) -> Executor:
        return self.executor_factory(verbose=verbose)


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


def executor_from_name(name: str, *, verbose: bool = False) -> Executor:
    """Create the execution backend configured for a CLI runner name."""
    return runner_config_from_name(name).create_executor(verbose=verbose)


def runner_executable_from_name(name: str) -> str:
    """Return the executable name configured for a public CLI runner name."""
    return runner_config_from_name(name).executable


def _record_published_outputs(
    runs: tuple[StepRun, ...],
) -> None:
    """Require published files and record their producer validation."""
    for run in runs:
        try:
            run.require_output_files()
        except FileNotFoundError as error:
            raise RuntimeError(
                f"CWL did not publish expected output(s) for "
                f"'{run.run_id}': {error}"
            ) from error
        try:
            record_validated_outputs(run)
        except OSError as error:
            logger.warning(
                "%s",
                prefix_log_lines(
                    (f"step:{run.run_id}",),
                    "Outputs are valid, but their validation receipt could "
                    f"not be written: {error}",
                ),
            )


def _requested_outputs(plan: ExecutionPlan) -> dict[str, Path]:
    """Return every requested output under its run-qualified name."""
    requested: dict[str, Path] = {}
    for run in plan.goals:
        paths = run.output_paths()
        for output in run.step.spec.outputs:
            requested[run.output(output).qualified_name] = paths[output.name]
    return requested


def _output_report_lines(plan: ExecutionPlan) -> list[str]:
    """Format requested output paths for a user-facing runner report."""
    requested = _requested_outputs(plan)
    qualify_names = len(plan.goals) != 1
    outputs = [
        (
            qualified_name
            if qualify_names
            else qualified_name.rsplit(".", maxsplit=1)[-1],
            path,
        )
        for qualified_name, path in requested.items()
    ]
    width = max(len(name) for name, _ in outputs)
    return [f"  {name:<{width}}: {path}" for name, path in outputs]


def _log_dry_run_plan(
    plan: ExecutionPlan,
    log_contexts: tuple[str, ...],
) -> None:
    """Log a grouped view of the inputs and resources for scheduled runs."""
    runs_to_execute = set(plan.runs_to_execute)
    count = len(plan.runs_to_execute)
    noun = "step" if count == 1 else "steps"
    lines = [f"Dry run: {count} {noun} would execute:"]

    for position, run in enumerate(plan.runs_to_execute, start=1):
        lines.extend(("", f"  {position}. {run.run_id}"))
        resolved = resolve_run_inputs(
            run,
            resolved_outputs=plan.resolved_outputs,
            runs_to_execute=runs_to_execute,
        )
        parameters: list[tuple[str, object]] = []
        inputs: list[tuple[str, str]] = []
        for input_name, resolved_input in resolved.items():
            if resolved_input.source == "scalar":
                if resolved_input.cwl_value is not None:
                    parameters.append((input_name, resolved_input.cwl_value))
                continue

            if resolved_input.source == "dep_wired":
                assert resolved_input.producer_output is not None
                detail = f"<- {resolved_input.producer_output.qualified_name}"
            elif resolved_input.source == "dep_disk":
                assert resolved_input.producer_output is not None
                path = resolved_input.path
                status = "OK" if path is not None and path.exists() else "MISSING"
                detail = (
                    f"<- {resolved_input.producer_output.qualified_name} "
                    f"({path}; {status})"
                )
            else:
                path = resolved_input.path
                status = "OK" if path is not None and path.exists() else "MISSING"
                detail = (
                    f"<- {path} (override {resolved_input.config_path}; "
                    f"{status})"
                )
            inputs.append((input_name, detail))

        if parameters:
            lines.append("     Parameters:")
            lines.extend(
                f"       {name}: {value}" for name, value in parameters
            )
        if inputs:
            width = max(len(name) for name, _ in inputs)
            lines.append("     Inputs:")
            lines.extend(
                f"       {name:<{width}} {detail}" for name, detail in inputs
            )
        if run.step.supports_multiple_processes:
            workers = cfg.step_resources(run.config, run.step)[
                cfg.RESOURCE_N_PROCESSES_KEY
            ]
            lines.extend(("     Resources:", f"       workers: {workers}"))

    _log_info(log_contexts, "\n".join(lines))


def run_plan(
    plan: ExecutionPlan,
    label: str,
    config: dict,
    *,
    dry_run: bool = False,
    executor: Executor | None = None,
    log_contexts: tuple[str, ...] | None = None,
) -> dict[str, Path]:
    """
    Execute an ExecutionPlan.

    A generated wrapper workflow and its generated step CommandLineTool files
    are written into a job bundle before execution.
    """

    executor = executor or CwlToolExecutor()
    log_contexts = log_contexts or (f"step:{label}",)

    if not plan.runs_to_execute:
        lines = [
            "Nothing to run; all outputs already exist",
            "",
            "Outputs:",
            *_output_report_lines(plan),
        ]
        _log_info(log_contexts, "\n".join(lines))
        return _requested_outputs(plan)

    cwl_bundle = generate_cwl_bundle(
        list(plan.runs_to_execute),
    )
    inputs = resolve_run_sequence_inputs(
        plan.runs_to_execute,
        plan.resolved_outputs,
    )
    last_run = plan.runs_to_execute[-1]

    if dry_run:
        _log_dry_run_plan(plan, log_contexts)
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
    logger.debug(
        "%s",
        prefix_log_lines(log_contexts, f"CWL job bundle written to {job_dir}"),
    )

    if len(plan.runs_to_execute) == 1:
        _log_info(log_contexts, "Running 1 step")
    else:
        _log_info(
            log_contexts,
            f"Running {len(plan.runs_to_execute)} steps",
        )
    datadir = Path(config["datadir"])
    executor.run(job_dir / "run.cwl", job_dir / "job.yml", datadir)
    _record_published_outputs(plan.runs_to_execute)
    lines = [
        "Completed successfully",
        "",
        "Outputs:",
        *_output_report_lines(plan),
        "",
        f"Job bundle: {job_dir}",
    ]
    _log_info(log_contexts, "\n".join(lines))
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
    registered_steps: dict[str, Step] | None = None,
    config_schema_paths: dict[str, Path] | None = None,
) -> dict[str, Path]:
    """Run an arbitrary list of Runnables as a single unified ExecutionPlan."""
    if not runnables:
        raise ValueError("run_all called with an empty runnables list.")

    label = ", ".join(r.name for r in runnables)
    log_contexts = tuple(_runnable_log_context(runnable) for runnable in runnables)
    plan = build_plan(
        runnables,
        config,
        non_recursive=non_recursive,
        force=force,
        _registry=registered_steps,
        _config_schema_paths=config_schema_paths,
    )
    return run_plan(
        plan,
        label,
        config,
        dry_run=dry_run,
        executor=executor,
        log_contexts=log_contexts,
    )


def export_all(
    runnables: list[Runnable],
    config: dict,
    *,
    recursive: bool = False,
    outdir: Path | None = None,
    runner_name: str = "cwltool",
    registered_steps: dict[str, Step] | None = None,
    config_schema_paths: dict[str, Path] | None = None,
) -> Path:
    """Export a complete runnable CWL bundle for the selected runnables."""
    if not runnables:
        raise ValueError("export_all called with an empty runnables list.")

    label = ", ".join(r.name for r in runnables)
    log_contexts = tuple(_runnable_log_context(runnable) for runnable in runnables)
    plan = build_export_plan(
        runnables,
        config,
        recursive=recursive,
        _registry=registered_steps,
        _config_schema_paths=config_schema_paths,
    )
    if not plan.runs_to_execute:
        raise RuntimeError("No steps were selected for export.")

    cwl_bundle = generate_cwl_bundle(
        list(plan.runs_to_execute),
    )
    inputs = resolve_run_sequence_inputs(
        plan.runs_to_execute,
        plan.resolved_outputs,
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
    _log_info(log_contexts, f"CWL export bundle written to {job_dir}")
    return job_dir
