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

from ASOkai._pipeline.base import Runnable
from ASOkai._pipeline.catalog import PipelineCatalog, get_pipeline_catalog
from ASOkai._pipeline import config as cfg
from ASOkai._pipeline import runner

from .options import (
    CONTEXT_SETTINGS,
    DEFAULT_CONFIG,
    parse_config_overrides,
    verbose_option,
)


def _collect_runnables(
    step_names: tuple[str, ...],
    task_names: tuple[str, ...],
    workflow_name: str | None,
    catalog: PipelineCatalog,
) -> list[Runnable]:
    """Resolve CLI selections to registered runnable objects."""
    runnables: list[Runnable] = []
    for name in step_names:
        if name not in catalog.steps:
            raise click.BadParameter(
                f"Unknown step '{name}'.",
                param_hint="--step",
            )
        runnables.append(catalog.steps[name])

    for name in task_names:
        if name not in catalog.tasks:
            raise click.BadParameter(
                f"Unknown task '{name}'.",
                param_hint="--task",
            )
        runnables.append(catalog.tasks[name])

    if workflow_name:
        if workflow_name not in catalog.workflows:
            raise click.BadParameter(
                f"Unknown workflow '{workflow_name}'.",
                param_hint="--workflow",
            )
        runnables.append(catalog.workflows[workflow_name])

    if not runnables:
        raise click.UsageError(
            "Select at least one runnable with " "--step, --task, or --workflow."
        )
    return runnables


@click.command("run", context_settings=CONTEXT_SETTINGS)
@verbose_option
@click.option(
    "-c",
    "--configfile",
    "--config-file",
    "config_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=DEFAULT_CONFIG,
    show_default=True,
    help="Path to config.yaml.",
)
@click.option(
    "--step",
    "step_names",
    multiple=True,
    metavar="NAME",
    help="Step to run. Repeat the option to select multiple steps.",
)
@click.option(
    "--task",
    "task_names",
    multiple=True,
    metavar="NAME",
    help="Task to run. Repeat the option to select multiple tasks.",
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
    "--non-recursive",
    is_flag=True,
    help="Require step dependencies to exist instead of running missing ones.",
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
    multiple=True,
    metavar="KEY=VALUE",
    help="Override a config value. Repeat the option for multiple values.",
)
def run_command(
    config_path: Path,
    step_names: tuple[str, ...],
    task_names: tuple[str, ...],
    workflow_name: str | None,
    force: bool,
    dry_run: bool,
    non_recursive: bool,
    executor_name: str,
    config_overrides: tuple[str, ...],
) -> None:
    """Run selected steps, tasks, or a workflow."""
    try:
        catalog = get_pipeline_catalog()
        runnables = _collect_runnables(
            step_names,
            task_names,
            workflow_name,
            catalog,
        )
        config = cfg.load(config_path)
        overrides = parse_config_overrides(config_overrides)
        cfg.apply_overrides(config, overrides)

        runner.run_all(
            runnables,
            config,
            force=force,
            dry_run=dry_run,
            non_recursive=non_recursive,
            executor=runner.executor_from_name(executor_name),
            registered_steps=catalog.steps,
            config_schema_paths=catalog.config_schema_paths,
        )
    except (OSError, RuntimeError, ValueError) as error:
        raise click.ClickException(str(error)) from error


@click.command("export", context_settings=CONTEXT_SETTINGS)
@verbose_option
@click.option(
    "-c",
    "--configfile",
    "--config-file",
    "config_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=DEFAULT_CONFIG,
    show_default=True,
    help="Path to config.yaml.",
)
@click.option(
    "--step",
    "step_names",
    multiple=True,
    metavar="NAME",
    help="Step to export. Repeat the option to select multiple steps.",
)
@click.option(
    "--task",
    "task_names",
    multiple=True,
    metavar="NAME",
    help="Task to export. Repeat the option to select multiple tasks.",
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
    help="Include every producer needed by the selected goals.",
)
@click.option(
    "--outdir",
    type=click.Path(file_okay=False, path_type=Path),
    default=None,
    metavar="DIR",
    help=(
        "Directory under which to write the export bundle. " "Defaults to datadir/jobs."
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
    multiple=True,
    metavar="KEY=VALUE",
    help="Override a config value. Repeat the option for multiple values.",
)
def export_command(
    config_path: Path,
    step_names: tuple[str, ...],
    task_names: tuple[str, ...],
    workflow_name: str | None,
    recursive: bool,
    outdir: Path | None,
    executor_name: str,
    config_overrides: tuple[str, ...],
) -> None:
    """Export selected pipeline units as a runnable CWL bundle."""
    try:
        catalog = get_pipeline_catalog()
        runnables = _collect_runnables(
            step_names,
            task_names,
            workflow_name,
            catalog,
        )
        config = cfg.load(config_path)
        overrides = parse_config_overrides(config_overrides)
        cfg.apply_overrides(config, overrides)

        export_directory = runner.export_all(
            runnables,
            config,
            recursive=recursive,
            outdir=outdir,
            runner_name=runner.runner_executable_from_name(executor_name),
            registered_steps=catalog.steps,
            config_schema_paths=catalog.config_schema_paths,
        )
    except (OSError, RuntimeError, ValueError) as error:
        raise click.ClickException(str(error)) from error

    click.echo(f"CWL export bundle written to {export_directory}")
