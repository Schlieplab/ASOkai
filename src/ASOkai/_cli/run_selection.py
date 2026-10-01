#!/usr/bin/env python
"""
Filename: src/ASOkai/_cli/run_selection.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Parse ordered CLI selections into YAML-style run declarations.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

from typing import Any

import click
import yaml

from ASOkai._pipeline.base import flatten_workflow_members
from ASOkai._pipeline.catalog import PipelineCatalog
from ASOkai._pipeline.steps.base import Step

_SELECTION_OPTIONS = {"--step": "step", "--task": "task", "--workflow": "workflow"}
_RUN_VALUE_OPTIONS = {
    *_SELECTION_OPTIONS,
    "--id",
    "--param",
    "--from-run",
    "--input-path",
    "--child",
}


def _assignment(value: str, option: str) -> tuple[str, str]:
    name, separator, assigned = value.partition("=")
    if not separator or not name or not assigned:
        raise click.BadParameter("Expected NAME=VALUE.", param_hint=option)
    return name, assigned


def parse_ordered_runs(
    args: list[str], ignored_value_options: set[str]
) -> list[dict[str, Any]]:
    """Keep selection and scoped override order before Click groups repeated options."""
    if "--help" in args or "-h" in args:
        return []
    runs: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    child: dict[str, Any] | None = None
    index = 0
    while index < len(args):
        token = args[index]
        if token == "--":
            break
        option, separator, attached = token.partition("=")
        if option in ignored_value_options:
            index += 1 if separator else 2
            continue
        if option not in _RUN_VALUE_OPTIONS:
            index += 1
            continue
        if separator:
            value = attached
            index += 1
        else:
            if index + 1 >= len(args):
                raise click.BadParameter("Requires a value.", param_hint=option)
            value = args[index + 1]
            index += 2

        if option in _SELECTION_OPTIONS:
            current = {_SELECTION_OPTIONS[option]: value}
            runs.append(current)
            child = None
            continue
        if current is None:
            raise click.UsageError(f"{option} must follow --step or --task.")
        if option == "--id":
            if child is not None or current.get("workflow") is not None:
                raise click.UsageError("--id must follow a top-level step or task.")
            if "id" in current:
                raise click.UsageError("A run may have only one --id.")
            current["id"] = value
            continue
        if option == "--child":
            if "task" not in current:
                raise click.UsageError("--child must follow a task selection.")
            child = {"id": value}
            current.setdefault("runs", []).append(child)
            continue
        if "workflow" in current:
            raise click.UsageError(
                "Workflow members cannot be configured directly; select a step or task."
            )
        target = child if child is not None else current
        if option == "--param":
            name, raw = _assignment(value, option)
            parameters = target.setdefault("parameters", {})
            if name in parameters:
                raise click.UsageError(f"Duplicate --param for '{name}'.")
            try:
                parameters[name] = yaml.safe_load(raw)
            except yaml.YAMLError as error:
                raise click.BadParameter(
                    f"Invalid YAML value: {error}", param_hint=option
                ) from error
            continue
        if target is current and "task" in current:
            raise click.UsageError(f"{option} requires --child for a task input.")
        name, source = _assignment(value, option)
        inputs = target.setdefault("inputs", {})
        if name in inputs:
            raise click.UsageError(f"Duplicate input selection for '{name}'.")
        if option == "--input-path":
            inputs[name] = {"path": source}
        else:
            run_id, dot, output = source.rpartition(".")
            if not dot or not run_id or not output:
                raise click.BadParameter(
                    "Expected INPUT=RUN_ID.OUTPUT.", param_hint=option
                )
            inputs[name] = {"from": f"run.{run_id}.{output}"}
    return runs


class OrderedRunCommand(click.Command):
    """Capture run options in command-line order before Click groups them."""

    def parse_args(self, ctx: click.Context, args: list[str]) -> list[str]:
        ignored_value_options = {
            option
            for parameter in self.params
            if isinstance(parameter, click.Option) and not parameter.is_flag
            for option in parameter.opts
        } - _RUN_VALUE_OPTIONS
        ctx.meta["asokai_ordered_runs"] = parse_ordered_runs(
            args, ignored_value_options
        )
        return super().parse_args(ctx, args)


def resolved_runs(
    selections: list[dict[str, Any]], catalog: PipelineCatalog
) -> list[dict[str, Any]]:
    """Validate names and expand workflow shorthand into YAML-style selections."""
    runs: list[dict[str, Any]] = []
    for selection in selections:
        if "step" in selection:
            name = selection["step"]
            if name not in catalog.steps:
                raise click.BadParameter(f"Unknown step '{name}'.", param_hint="--step")
            runs.append(selection)
        elif "task" in selection:
            name = selection["task"]
            if name not in catalog.tasks:
                raise click.BadParameter(f"Unknown task '{name}'.", param_hint="--task")
            runs.append(selection)
        else:
            name = selection["workflow"]
            workflow = catalog.workflows.get(name)
            if workflow is None:
                raise click.BadParameter(
                    f"Unknown workflow '{name}'.", param_hint="--workflow"
                )
            for member in flatten_workflow_members(workflow):
                kind = "step" if isinstance(member, Step) else "task"
                runs.append({kind: member.name})
    return runs
