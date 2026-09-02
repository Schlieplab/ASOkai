#!/usr/bin/env python
"""
Filename: src/ASOkai/_cli/catalog.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Version: 0.1.1
Description: Commands for listing and describing ASOkai pipeline units.
License: LGPL-3.0-or-later
"""
from __future__ import annotations

from collections.abc import Sequence
from itertools import groupby
from typing import Any

import click

from ASOkai._pipeline.catalog import PipelineCatalog, get_pipeline_catalog
from ASOkai._pipeline.steps.analysis.base import AnalysisStep
from ASOkai._pipeline.steps.core.base import CoreStep

from .options import CONTEXT_SETTINGS, verbose_option


def _step_category_path(step: object) -> tuple[str, ...]:
    """Return the CLI category path for a step."""
    if isinstance(step, CoreStep):
        return ("core",)
    if isinstance(step, AnalysisStep):
        return ("analysis",)
    return ("pipeline",)


def _step_type_label(step: object) -> str:
    """Return the CLI display label for a step type."""
    return " / ".join(
        part.capitalize()
        for part in _step_category_path(step)
    )


def _analysis_scope_label(
    analysis_class: type | None,
) -> str | None:
    """Return the analysis scope declared by an analysis class."""
    if analysis_class is None:
        return None
    return getattr(analysis_class, "scope_label", None)


def _display_description(pipeline_unit: object) -> str:
    """Return the description displayed for a pipeline unit."""
    description = getattr(pipeline_unit, "description", "")
    if isinstance(pipeline_unit, AnalysisStep):
        scope = _analysis_scope_label(
            getattr(pipeline_unit, "analysis_cls", None)
        )
        if scope:
            return f"[{scope}] {description}"
    return description


@click.command("list", context_settings=CONTEXT_SETTINGS)
@click.argument(
    "unit",
    type=click.Choice(["steps", "tasks", "workflows"]),
)
def list_command(unit: str) -> None:
    """List available steps, tasks, or workflows."""
    catalog = get_pipeline_catalog()
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
        category_order = {"core": 0, "analysis": 1}
        rows = sorted(
            registry.items(),
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
            click.echo(
                " / ".join(
                    part.capitalize()
                    for part in category
                )
            )
            for name, pipeline_unit in items:
                click.echo(
                    f"  {name:<{name_width}} "
                    f"{_display_description(pipeline_unit)}"
                )
        return

    for name, pipeline_unit in sorted(registry.items()):
        click.echo(
            f"  {name:<{name_width}} "
            f"{_display_description(pipeline_unit)}"
        )


def _expanded_step_names(members: Sequence) -> list[str]:
    """Recursively expand workflow members into ordered explicit steps."""
    from ASOkai._pipeline.steps.base import Step
    from ASOkai._pipeline.tasks.base import Task
    from ASOkai._pipeline.workflows.base import Workflow

    step_names: list[str] = []
    for member in members:
        if isinstance(member, Workflow):
            step_names.extend(_expanded_step_names(member.members))
        elif isinstance(member, Task):
            step_names.extend(step.name for step in member.steps)
        elif isinstance(member, Step):
            step_names.append(member.name)
    return step_names


def _dependency_name(dependency) -> str:
    """Return the registry name of a dependency."""
    return getattr(dependency, "name", dependency)


def _dependency_tree_lines(
    registry: dict,
    dependencies: list[str],
    prefix: str = "",
    seen: set[str] | None = None,
) -> list[str]:
    """Build dependency-tree lines while avoiding cycles."""
    seen = seen or set()
    lines = []
    for index, dependency in enumerate(dependencies):
        dependency_name = _dependency_name(dependency)
        is_last = index == len(dependencies) - 1
        connector = "`-- " if is_last else "|-- "

        if dependency_name in seen:
            lines.append(
                f"{prefix}{connector}{dependency_name} (cycle)"
            )
            continue

        lines.append(f"{prefix}{connector}{dependency_name}")
        dependency_unit = registry.get(dependency_name)
        if dependency_unit is None:
            continue

        nested_dependencies = (
            getattr(dependency_unit, "dependencies", None)
            or getattr(dependency_unit, "steps", None)
            or []
        )
        child_prefix = f"{prefix}{'    ' if is_last else '|   '}"
        lines.extend(
            _dependency_tree_lines(
                registry,
                nested_dependencies,
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


def _describe_step_config_keys(step) -> None:
    """Print the configurable keys of a step."""
    config_params = [
        param
        for param in step.spec.params
        if param.config
    ]
    if not config_params:
        return

    click.echo("Config keys :")
    for param in config_params:
        click.echo(
            f"  --config {param.config:<32}"
            f"{_config_hint_for_param(param)}"
        )


def _describe_step_input_configuration(step) -> None:
    """Print optional configuration paths for the step's file inputs."""
    if not step.spec.inputs:
        return

    click.echo("Input configuration (optional):")
    for file_input in step.spec.inputs:
        configuration_path = file_input.configuration_path(step.name)
        click.echo(
            f"  --config {configuration_path}.path_override  existing file"
        )
        for name in file_input.configurable_parameters:
            click.echo(
                f"  --config {configuration_path}.parameters.{name}  "
                "separate producer-run value"
            )


def _describe_step(step) -> tuple[list[str], str]:
    """Print step details and return its dependency summary."""
    click.echo(f"Type        : {_step_type_label(step)}")
    _describe_step_config_keys(step)
    _describe_step_input_configuration(step)
    return step.dependencies or [], "Dependencies"


def _describe_task(task) -> tuple[list[str], str]:
    """Print task details and return its step summary."""
    step_names = [step.name for step in task.steps]
    click.echo(f"Steps       : {', '.join(step_names)}")
    click.echo("CWL         : (CLI collection; export creates run.cwl)")
    return step_names, "Steps"


def _describe_workflow(workflow) -> tuple[list[str], str]:
    """Print workflow details and return its expanded step summary."""
    member_names = [member.name for member in workflow.members]
    click.echo(f"Members     : {', '.join(member_names)}")
    click.echo("CWL         : (CLI collection; export creates run.cwl)")
    return _expanded_step_names(workflow.members), "Steps (expanded)"


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
        registry = {
            **catalog.steps,
            **catalog.tasks,
            **catalog.workflows,
        }
        click.echo(f"{label}:")
        for line in _dependency_tree_lines(registry, dependencies):
            click.echo(f"  {line}")
    else:
        click.echo(
            f"{label}: "
            f"{', '.join(str(value) for value in dependencies)}"
        )


@click.command("describe", context_settings=CONTEXT_SETTINGS)
@verbose_option
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
    catalog = get_pipeline_catalog()
    registry = {
        "step": catalog.steps,
        "task": catalog.tasks,
        "workflow": catalog.workflows,
    }[unit]
    pipeline_unit = registry.get(name)
    if pipeline_unit is None:
        raise click.ClickException(f"Unknown {unit} '{name}'.")

    click.echo(f"Name        : {pipeline_unit.name}")
    click.echo(
        f"Description : {_display_description(pipeline_unit)}"
    )

    if unit == "step":
        dependencies, label = _describe_step(pipeline_unit)
    elif unit == "task":
        dependencies, label = _describe_task(pipeline_unit)
    else:
        dependencies, label = _describe_workflow(pipeline_unit)

    _describe_dependencies(
        label,
        dependencies,
        unit,
        ctx.obj.get("verbose", False),
        catalog,
    )
