#!/usr/bin/env python
"""
Filename: src/ASOkai/_cli/execution.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Version: 0.1.1
Description: Commands for running and exporting ASOkai pipeline units.
License: LGPL-3.0-or-later
"""
from __future__ import annotations

from pathlib import Path

import click

from ASOkai.Plugins._registry import get_steps, get_tasks, get_workflows
from ASOkai._pipeline import config as cfg
from ASOkai._pipeline import runner

from .options import (
    CONTEXT_SETTINGS,
    DEFAULT_CONFIG,
    VariadicOption,
    flatten_option_values,
    parse_config_overrides,
    verbose_option,
)


def _collect_runnables(
    step_names: tuple[str, ...],
    task_names: tuple[str, ...],
    workflow_name: str | None,
) -> list:
    """Resolve CLI selections to registered runnable objects."""
    steps = get_steps()
    tasks = get_tasks()
    workflows = get_workflows()

    runnables = []
    for name in flatten_option_values(step_names):
        if name not in steps:
            raise click.BadParameter(
                f"Unknown step '{name}'.",
                param_hint="--steps",
            )
        runnables.append(steps[name])

    for name in flatten_option_values(task_names):
        if name not in tasks:
            raise click.BadParameter(
                f"Unknown task '{name}'.",
                param_hint="--tasks",
            )
        runnables.append(tasks[name])

    if workflow_name:
        if workflow_name not in workflows:
            raise click.BadParameter(
                f"Unknown workflow '{workflow_name}'.",
                param_hint="--workflow",
            )
        runnables.append(workflows[workflow_name])

    if not runnables:
        raise click.UsageError(
            "Select at least one runnable with "
            "--steps, --tasks, or --workflow."
        )
    return runnables


@click.command("run", context_settings=CONTEXT_SETTINGS)
@verbose_option
@click.option(
    "-c",
    "--configfile",
    "--config-file",
    "config_path",
    type=click.Path(exists=True, path_type=Path),
    default=DEFAULT_CONFIG,
    show_default=True,
    help="Path to config.yaml.",
)
@click.option(
    "--steps",
    "step_names",
    cls=VariadicOption,
    multiple=True,
    type=click.UNPROCESSED,
    metavar="NAME [NAME ...]",
    help="Step(s) to run. Repeat the flag or pass multiple names.",
)
@click.option(
    "--tasks",
    "task_names",
    cls=VariadicOption,
    multiple=True,
    type=click.UNPROCESSED,
    metavar="NAME [NAME ...]",
    help="Task(s) to run. Repeat the flag or pass multiple names.",
)
@click.option(
    "--workflow",
    "workflow_name",
    default=None,
    metavar="NAME",
    help="Workflow to run.",
)
@click.option(
    "--force",
    is_flag=True,
    help="Re-run even if outputs already exist.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would run without executing.",
)
@click.option(
    "--recursive",
    is_flag=True,
    help="Automatically run missing step dependencies.",
)
@click.option(
    "--executor",
    "executor_name",
    type=click.Choice(runner.RUNNER_NAMES),
    default="cwltool",
    show_default=True,
    help="CWL executor backend.",
)
@click.option(
    "--config",
    "config_overrides",
    cls=VariadicOption,
    multiple=True,
    type=click.UNPROCESSED,
    metavar="KEY=VALUE [KEY=VALUE ...]",
    help="Override config values.",
)
def run_command(
    config_path: Path,
    step_names: tuple[str, ...],
    task_names: tuple[str, ...],
    workflow_name: str | None,
    force: bool,
    dry_run: bool,
    recursive: bool,
    executor_name: str,
    config_overrides: tuple,
) -> None:
    """Run selected steps, tasks, or a workflow."""
    config = cfg.load(config_path)

    overrides = parse_config_overrides(config_overrides)
    if overrides:
        cfg.apply_overrides(config, overrides)

    runnables = _collect_runnables(
        step_names,
        task_names,
        workflow_name,
    )
    runner.run_all(
        runnables,
        config,
        force=force,
        dry_run=dry_run,
        recursive=recursive,
        executor=runner.executor_from_name(executor_name),
    )


@click.command("export", context_settings=CONTEXT_SETTINGS)
@verbose_option
@click.option(
    "-c",
    "--configfile",
    "--config-file",
    "config_path",
    type=click.Path(exists=True, path_type=Path),
    default=DEFAULT_CONFIG,
    show_default=True,
    help="Path to config.yaml.",
)
@click.option(
    "--steps",
    "step_names",
    cls=VariadicOption,
    multiple=True,
    type=click.UNPROCESSED,
    metavar="NAME [NAME ...]",
    help="Step(s) to export. Repeat the flag or pass multiple names.",
)
@click.option(
    "--tasks",
    "task_names",
    cls=VariadicOption,
    multiple=True,
    type=click.UNPROCESSED,
    metavar="NAME [NAME ...]",
    help="Task(s) to export. Repeat the flag or pass multiple names.",
)
@click.option(
    "--workflow",
    "workflow_name",
    default=None,
    metavar="NAME",
    help="Workflow to export.",
)
@click.option(
    "--recursive",
    is_flag=True,
    help="Include missing step dependencies in the exported plan.",
)
@click.option(
    "--outdir",
    type=click.Path(path_type=Path),
    default=None,
    metavar="DIR",
    help=(
        "Directory under which to write the export bundle. "
        "Defaults to datadir/jobs."
    ),
)
@click.option(
    "--executor",
    "executor_name",
    type=click.Choice(runner.RUNNER_NAMES),
    default="cwltool",
    show_default=True,
    help="CWL executor backend documented in the export README.",
)
@click.option(
    "--config",
    "config_overrides",
    cls=VariadicOption,
    multiple=True,
    type=click.UNPROCESSED,
    metavar="KEY=VALUE [KEY=VALUE ...]",
    help="Override config values.",
)
def export_command(
    config_path: Path,
    step_names: tuple[str, ...],
    task_names: tuple[str, ...],
    workflow_name: str | None,
    recursive: bool,
    outdir: Path | None,
    executor_name: str,
    config_overrides: tuple,
) -> None:
    """Export selected pipeline units as a runnable CWL bundle."""
    config = cfg.load(config_path)

    overrides = parse_config_overrides(config_overrides)
    if overrides:
        cfg.apply_overrides(config, overrides)

    runnables = _collect_runnables(
        step_names,
        task_names,
        workflow_name,
    )
    try:
        export_directory = runner.export_all(
            runnables,
            config,
            recursive=recursive,
            outdir=outdir,
            runner_name=runner.runner_name_from_name(executor_name),
        )
    except RuntimeError as error:
        raise click.ClickException(str(error)) from error

    click.echo(
        f"CWL export bundle written to {export_directory}"
    )
