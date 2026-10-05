#!/usr/bin/env python
"""
Filename: src/ASOkai/_cli/catalog.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Commands for listing and describing ASOkai pipeline units.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

from itertools import groupby
from typing import Any

import click

from ASOkai.Analysis import PerUnitAnalysis
from ASOkai._pipeline.base import expand_runnable_steps
from ASOkai._pipeline.catalog import PipelineCatalog, get_pipeline_catalog
from ASOkai._pipeline.steps.analysis.base import AnalysisStep
from ASOkai._pipeline.steps.base import Step
from ASOkai._pipeline.steps.core.base import CoreStep
from ASOkai._pipeline.steps.utils.base import UtilityStep
from ASOkai._pipeline.tasks.base import validate_task_outputs

from .options import (
    CONTEXT_SETTINGS,
    catalog_verbose_option,
    describe_verbose_option,
)


def _step_category_path(step: object) -> tuple[str, ...]:
    """Return the CLI category path for a step."""
    if isinstance(step, Step) and not step.listed:
        return ("internal",)
    if isinstance(step, CoreStep):
        return ("core",)
    if isinstance(step, AnalysisStep):
        return ("analysis",)
    if isinstance(step, UtilityStep):
        return ("utils",)
    return ("pipeline",)


def _step_type_label(step: object) -> str:
    """Return the CLI display label for a step type."""
    return " / ".join(part.capitalize() for part in _step_category_path(step))


def _analysis_unit_label(
    analysis_class: type | None,
) -> str | None:
    """Return a label for the analysis unit type and execution model."""
    if analysis_class is None:
        return None
    unit_type = getattr(analysis_class, "analysis_unit_type", None)
    if not isinstance(unit_type, str):
        return None
    if issubclass(analysis_class, PerUnitAnalysis):
        return f"Per {unit_type}"
    return unit_type.capitalize()


def _display_description(pipeline_unit: object) -> str:
    """Return the description displayed for a pipeline unit."""
    description = getattr(pipeline_unit, "description", "")
    if isinstance(pipeline_unit, AnalysisStep):
        label = _analysis_unit_label(getattr(pipeline_unit, "analysis_cls", None))
        if label:
            return f"[{label}] {description}"
    return description


@click.command("list", context_settings=CONTEXT_SETTINGS)
@catalog_verbose_option
@click.argument(
    "unit",
    type=click.Choice(["steps", "tasks", "workflows"]),
)
@click.pass_context
def list_command(ctx: click.Context, unit: str) -> None:
    """List available steps, tasks, or workflows."""
    try:
        catalog = get_pipeline_catalog()
    except ValueError as error:
        raise click.ClickException(str(error)) from error
    registry = {
        "steps": catalog.steps,
        "tasks": catalog.tasks,
        "workflows": catalog.workflows,
    }[unit]
    if not registry:
        click.echo(f"No {unit} available.")
        return

    name_width = max(len(name) for name in registry) + 2

    if unit == "steps":
        category_order = {"core": 0, "analysis": 1, "utils": 2, "internal": 3}
        rows = sorted(
            (
                (name, step)
                for name, step in registry.items()
                if step.listed or ctx.obj.get("verbose", False)
            ),
            key=lambda item: (
                category_order.get(
                    _step_category_path(item[1])[0],
                    99,
                ),
                _step_category_path(item[1]),
                item[0],
            ),
        )
        for index, (category, items) in enumerate(
            groupby(
                rows,
                key=lambda item: _step_category_path(item[1]),
            )
        ):
            if index:
                click.echo()
            click.echo(" / ".join(part.capitalize() for part in category))
            for name, pipeline_unit in items:
                click.echo(
                    f"  {name:<{name_width}} " f"{_display_description(pipeline_unit)}"
                )
        return

    for name, pipeline_unit in sorted(registry.items()):
        click.echo(f"  {name:<{name_width}} " f"{_display_description(pipeline_unit)}")


def _dependency_tree_lines(
    steps: dict[str, Step],
    dependencies: list[str],
    prefix: str = "",
    seen: set[str] | None = None,
) -> list[str]:
    """Build dependency-tree lines while avoiding cycles."""
    seen = seen or set()
    lines = []
    for index, dependency_name in enumerate(dependencies):
        is_last = index == len(dependencies) - 1
        connector = "`-- " if is_last else "|-- "

        if dependency_name in seen:
            lines.append(f"{prefix}{connector}{dependency_name} (cycle)")
            continue

        lines.append(f"{prefix}{connector}{dependency_name}")
        dependency_step = steps.get(dependency_name)
        if dependency_step is None:
            continue

        child_prefix = f"{prefix}{'    ' if is_last else '|   '}"
        lines.extend(
            _dependency_tree_lines(
                steps,
                dependency_step.dependencies,
                child_prefix,
                seen | {dependency_name},
            )
        )
    return lines


def _config_hint_for_param(param: Any) -> str:
    """Return a compact configuration hint for a step parameter."""
    choices = param.parser_choices()
    if choices:
        return f"  {' | '.join(str(choice) for choice in choices)}"

    if param.parser_type() is int:
        return "  int"

    doc = getattr(param, "doc", None)
    return f"  {doc}" if doc else ""


def _describe_step_parameters(step, *, verbose: bool) -> None:
    """Print run parameters, with shared configuration keys when requested."""
    if not step.spec.params:
        return

    click.echo("Run parameters:")
    for param in step.spec.params:
        click.echo(f"  --param {param.name}=VALUE{_config_hint_for_param(param)}")
        if verbose and param.config:
            click.echo(f"    config key: {param.config}")


def _describe_step_inputs(step, *, verbose: bool) -> None:
    """Print file inputs and explain selection only in the detailed view."""
    if not step.spec.inputs:
        click.echo("Inputs: (none)")
        return

    click.echo("Inputs:")
    for file_input in step.spec.inputs:
        source = file_input.source
        origin = (
            f"  from {source.producer}.{source.name} by default"
            if source is not None
            else "  supply a file or link a run"
        )
        click.echo(
            f"  {file_input.name:<20} {file_input.file_type.format_name}{origin}"
        )
        if verbose:
            if file_input.doc:
                click.echo(f"    {file_input.doc}")
            click.echo(
                f"    CLI: --input-path {file_input.name}=PATH or "
                f"--from-run {file_input.name}=RUN_ID.OUTPUT"
            )
            click.echo(
                "    Existing file in config.yaml: "
                f"{file_input.configuration_path(step.name)}.path_override"
            )


def _describe_step_outputs(step, *, verbose: bool) -> None:
    """Print declared output ports and their destinations when requested."""
    if not step.spec.outputs:
        click.echo("Outputs: (none)")
        return

    click.echo("Outputs:")
    for output in step.spec.outputs:
        click.echo(f"  {output.name:<20} {output.file_type.format_name}")
        if verbose:
            if output.doc:
                click.echo(f"    {output.doc}")
            click.echo(f"    Under datadir: {output.destination.template}")


def _describe_step(step, *, verbose: bool) -> tuple[list[str], str]:
    """Print step details and return its dependency summary."""
    click.echo(f"Type        : {_step_type_label(step)}")
    _describe_step_parameters(step, verbose=verbose)
    _describe_step_inputs(step, verbose=verbose)
    _describe_step_outputs(step, verbose=verbose)
    return step.dependencies, "Dependencies"


def _describe_task(task, *, verbose: bool) -> None:
    """Print child steps, open inputs, and exposed task outputs."""
    step_names = [step.name for step in task.steps]
    click.echo(f"Steps       : {', '.join(step_names)}")
    runs = getattr(task, "runs", ())
    open_inputs = [
        (run.run_id, file_input)
        for run in runs
        for file_input in run.step.spec.inputs
        if file_input.name not in run.inputs
    ]
    if open_inputs:
        click.echo("Inputs:")
        for run_id, file_input in open_inputs:
            qualified_name = f"{run_id}.{file_input.name}"
            source = file_input.source
            origin = (
                f"  from {source.producer}.{source.name} by default"
                if source is not None
                else "  supply a file or link a run"
            )
            details = f"{file_input.file_type.format_name}{origin}"
            click.echo(f"  {qualified_name:<24} {details}")
            if verbose:
                click.echo(
                    f"    CLI: --child {run_id} --input-path {file_input.name}=PATH"
                )
    else:
        click.echo("Inputs: (none at task boundary)")
    outputs = validate_task_outputs(task) if runs else {}
    runs_by_id = {run.run_id: run for run in runs}
    if outputs:
        click.echo("Outputs:")
        for name, reference in outputs.items():
            output = runs_by_id[reference.run_id].step.spec.output(
                reference.output_name
            )
            click.echo(
                f"  {name:<20} {output.file_type.format_name} "
                f"from {reference.run_id}.{reference.output_name}"
            )
    else:
        click.echo("Outputs: (none exposed; use a child run output)")
    if verbose and runs:
        click.echo("Child runs:")
        for run in runs:
            click.echo(f"  {run.run_id:<20} {run.step.name}")
    click.echo("CWL         : (CLI collection; export creates run.cwl)")


def _describe_workflow(workflow) -> tuple[list[str], str]:
    """Print workflow details and return its expanded step summary."""
    member_names = [member.name for member in workflow.members]
    click.echo(f"Members     : {', '.join(member_names)}")
    click.echo("CWL         : (CLI collection; export creates run.cwl)")
    return [step.name for step in expand_runnable_steps(workflow)], "Steps (expanded)"


def _describe_dependencies(
    label: str,
    dependencies: list[str],
    unit: str,
    verbose: bool,
    catalog: PipelineCatalog,
) -> None:
    """Print a dependency summary."""
    if not dependencies:
        click.echo(f"{label}: (none)")
    elif verbose and unit == "step":
        click.echo(f"{label}:")
        for line in _dependency_tree_lines(catalog.steps, dependencies):
            click.echo(f"  {line}")
    else:
        click.echo(f"{label}: " f"{', '.join(str(value) for value in dependencies)}")


@click.command("describe", context_settings=CONTEXT_SETTINGS)
@describe_verbose_option
@click.argument(
    "unit",
    type=click.Choice(["step", "task", "workflow"]),
)
@click.argument("name")
@click.pass_context
def describe_command(
    ctx: click.Context,
    unit: str,
    name: str,
) -> None:
    """Describe a step, task, or workflow."""
    try:
        catalog = get_pipeline_catalog()
    except ValueError as error:
        raise click.ClickException(str(error)) from error
    registry = {
        "step": catalog.steps,
        "task": catalog.tasks,
        "workflow": catalog.workflows,
    }[unit]
    pipeline_unit = registry.get(name)
    if pipeline_unit is None or (
        unit == "step"
        and not pipeline_unit.listed
        and not ctx.obj.get("verbose", False)
    ):
        raise click.ClickException(f"Unknown {unit} '{name}'.")

    click.echo(f"Name        : {pipeline_unit.name}")
    click.echo(f"Description : {_display_description(pipeline_unit)}")

    if unit == "task":
        _describe_task(
            pipeline_unit,
            verbose=ctx.obj.get("verbose", False),
        )
        return
    if unit == "step":
        dependencies, label = _describe_step(
            pipeline_unit,
            verbose=ctx.obj.get("verbose", False),
        )
    else:
        dependencies, label = _describe_workflow(pipeline_unit)
    _describe_dependencies(
        label,
        dependencies,
        unit,
        ctx.obj.get("verbose", False),
        catalog,
    )
