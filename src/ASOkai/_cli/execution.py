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

from ASOkai._pipeline.catalog import PipelineCatalog, get_pipeline_catalog
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
    catalog: PipelineCatalog,
) -> list:
    """Resolve CLI selections to registered runnable objects."""
    runnables = []
    for name in flatten_option_values(step_names):
        if name not in catalog.steps:
            raise click.BadParameter(
                f"Unknown step '{name}'.",
                param_hint="--steps",
            )
        runnables.append(catalog.steps[name])

    for name in flatten_option_values(task_names):
        if name not in catalog.tasks:
            raise click.BadParameter(
                f"Unknown task '{name}'.",
                param_hint="--tasks",
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
    non_recursive: bool,
    executor_name: str,
    config_overrides: tuple,
) -> None:
    """Run selected steps, tasks, or a workflow."""
    catalog = get_pipeline_catalog()
    runnables = _collect_runnables(
        step_names,
        task_names,
        workflow_name,
        catalog,
    )
    try:
        config = cfg.load(
            config_path,
            plugin_schema_paths=catalog.config_schema_paths,
            registered_steps=catalog.steps,
        )
        overrides = parse_config_overrides(config_overrides)
        if overrides:
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
    help="Include every producer needed by the selected goals.",
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
    catalog = get_pipeline_catalog()
    runnables = _collect_runnables(
        step_names,
        task_names,
        workflow_name,
        catalog,
    )
    try:
        config = cfg.load(
            config_path,
            plugin_schema_paths=catalog.config_schema_paths,
            registered_steps=catalog.steps,
        )
        overrides = parse_config_overrides(config_overrides)
        if overrides:
            cfg.apply_overrides(config, overrides)

        export_directory = runner.export_all(
            runnables,
            config,
            recursive=recursive,
            outdir=outdir,
            runner_name=runner.runner_name_from_name(executor_name),
            registered_steps=catalog.steps,
            config_schema_paths=catalog.config_schema_paths,
        )
    except (OSError, RuntimeError, ValueError) as error:
        raise click.ClickException(str(error)) from error

    click.echo(
        f"CWL export bundle written to {export_directory}"
    )
