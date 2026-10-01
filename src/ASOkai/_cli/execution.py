#!/usr/bin/env python
"""
Filename: src/ASOkai/_cli/execution.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Commands for running and exporting ASOkai pipeline units.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

from pathlib import Path

import click

from ASOkai._pipeline import config as cfg
from ASOkai._pipeline import runner
from ASOkai._pipeline.catalog import PipelineCatalog, get_pipeline_catalog

from .options import (
    CONTEXT_SETTINGS,
    DEFAULT_CONFIG,
    verbose_option,
)
from .run_selection import OrderedRunCommand, resolved_runs


def _run_selection_options(command):
    """Add per-run options to both execution commands."""
    for option, help_text in (
        ("--id", "ID for the preceding step or task."),
        ("--param", "Parameter NAME=VALUE for the current run."),
        ("--from-run", "Input INPUT=RUN_ID.OUTPUT for the current run."),
        ("--input-path", "Input INPUT=PATH for the current run."),
        ("--child", "Declared child ID of the preceding task."),
    ):
        command = click.option(
            option,
            multiple=True,
            metavar="VALUE",
            expose_value=False,
            help=help_text,
        )(command)
    return command


def _configured_cli_runs(
    ctx: click.Context, config: dict, catalog: PipelineCatalog
) -> None:
    """Feed CLI and YAML selections through the same run normalization path."""
    selections = ctx.meta["asokai_ordered_runs"]
    if selections and "runs" in config:
        raise click.UsageError(
            "Select runs in the configuration or with --step/--task/--workflow, not both."
        )
    if selections:
        config["runs"] = resolved_runs(selections, catalog)
    elif "runs" not in config:
        raise click.UsageError(
            "Select at least one runnable with --step, --task, or --workflow."
        )


@click.command("run", context_settings=CONTEXT_SETTINGS, cls=OrderedRunCommand)
@verbose_option
@_run_selection_options
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
    multiple=True,
    expose_value=False,
    metavar="NAME",
    help="Step to run. Repeat the option to select multiple steps.",
)
@click.option(
    "--task",
    multiple=True,
    expose_value=False,
    metavar="NAME",
    help="Task to run. Repeat the option to select multiple tasks.",
)
@click.option(
    "--workflow",
    default=None,
    expose_value=False,
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
@click.pass_context
def run_command(
    ctx: click.Context,
    config_path: Path,
    force: bool,
    dry_run: bool,
    non_recursive: bool,
    executor_name: str,
) -> None:
    """Run selected steps, tasks, or a workflow."""
    try:
        catalog = get_pipeline_catalog()
        config = cfg.load(config_path)
        _configured_cli_runs(ctx, config, catalog)

        verbose = bool(ctx.obj and ctx.obj.get("verbose", False))
        runner.run_all(
            [],
            config,
            force=force,
            dry_run=dry_run,
            non_recursive=non_recursive,
            executor=runner.executor_from_name(
                executor_name,
                verbose=verbose,
            ),
            registered_steps=catalog.steps,
            registered_tasks=catalog.tasks,
            config_schema_paths=catalog.config_schema_paths,
        )
    except (OSError, RuntimeError, ValueError) as error:
        raise click.ClickException(str(error)) from error


@click.command("export", context_settings=CONTEXT_SETTINGS, cls=OrderedRunCommand)
@verbose_option
@_run_selection_options
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
    multiple=True,
    expose_value=False,
    metavar="NAME",
    help="Step to export. Repeat the option to select multiple steps.",
)
@click.option(
    "--task",
    multiple=True,
    expose_value=False,
    metavar="NAME",
    help="Task to export. Repeat the option to select multiple tasks.",
)
@click.option(
    "--workflow",
    default=None,
    expose_value=False,
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
@click.pass_context
def export_command(
    ctx: click.Context,
    config_path: Path,
    recursive: bool,
    outdir: Path | None,
    executor_name: str,
) -> None:
    """Export selected pipeline units as a runnable CWL bundle."""
    try:
        catalog = get_pipeline_catalog()
        config = cfg.load(config_path)
        _configured_cli_runs(ctx, config, catalog)

        export_directory = runner.export_all(
            [],
            config,
            recursive=recursive,
            outdir=outdir,
            runner_name=runner.runner_executable_from_name(executor_name),
            registered_steps=catalog.steps,
            registered_tasks=catalog.tasks,
            config_schema_paths=catalog.config_schema_paths,
        )
    except (OSError, RuntimeError, ValueError) as error:
        raise click.ClickException(str(error)) from error

    click.echo(f"CWL export bundle written to {export_directory}")
