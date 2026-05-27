"""
Filename: src/cli/main.py
Description: ASOkai CLI entry point.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

import argparse
import importlib
import logging
from pathlib import Path
from types import ModuleType
from typing import Callable, Literal, cast

import click
import yaml

from ASOkai._pipeline import config as cfg
from ASOkai._pipeline import runner
from ASOkai._cwl.executors import CwlToolExecutor, ToilExecutor
from ASOkai._pipeline.registry import get_steps, get_tasks, get_workflows

DEFAULT_CONFIG = Path("config.yaml")


class _VariadicOption(click.Option):
    """Click option that consumes values until the next option."""

    def add_to_parser(self, parser, ctx):
        retval = super().add_to_parser(parser, ctx)
        for name in self.opts:
            option_parser = parser._long_opt.get(name) or parser._short_opt.get(name)
            if option_parser is None:
                continue

            previous_process = option_parser.process

            def parser_process(value, state, previous_process=previous_process):
                values = [value]
                while state.rargs:
                    next_arg = state.rargs[0]
                    if next_arg.startswith("-"):
                        break
                    values.append(state.rargs.pop(0))
                previous_process(tuple(values), state)

            option_parser.process = parser_process
        return retval


class _OptionalPathOption(click.Option):
    """Click flag that optionally consumes one following path value."""

    def __init__(self, *args, **kwargs):
        super().__init__(
            *args,
            is_flag=True,
            flag_value=True,
            default=None,
            type=click.UNPROCESSED,
            **kwargs,
        )

    def add_to_parser(self, parser, ctx):
        retval = super().add_to_parser(parser, ctx)
        for name in self.opts:
            option_parser = parser._long_opt.get(name) or parser._short_opt.get(name)
            if option_parser is None:
                continue

            def parser_process(value, state, option_parser=option_parser):
                if state.rargs:
                    next_arg = state.rargs[0]
                    if not next_arg.startswith("-"):
                        value = state.rargs.pop(0)
                    else:
                        value = True
                else:
                    value = True
                state.opts[option_parser.dest] = value
                state.order.append(option_parser.obj)

            option_parser.process = parser_process
        return retval


def _set_verbose(ctx: click.Context, param: click.Parameter, value: bool) -> bool:
    if value:
        logging.getLogger().setLevel(logging.DEBUG)
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = value
    return value

verbose_option = click.option(
    "-v", "--verbose",
    is_flag=True,
    is_eager=True,
    expose_value=False,
    callback=_set_verbose,
    help="Enable debug logging.",
)


@click.group()
@click.pass_context
def main(ctx: click.Context) -> None:
    """ASOkai — ASO design pipeline."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    ctx.ensure_object(dict)


def _resolve_step_module(step_name: str) -> ModuleType:
    """Return the module declared by a registered step's ``cli_module``."""
    step = get_steps().get(step_name)
    if step is None:
        raise KeyError(step_name)
    return importlib.import_module(step.cli_module)


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------

@main.command("list")
@click.argument("unit", type=click.Choice(["steps", "tasks", "workflows"]))
def list_cmd(unit: str) -> None:
    """List available steps, tasks, or workflows."""
    registry = {
        "steps": get_steps,
        "tasks": get_tasks,
        "workflows": get_workflows,
    }[unit]()
    if not registry:
        click.echo(f"No {unit} available.")
        return
    for name, obj in sorted(registry.items()):
        click.echo(f"  {name:<35} {obj.description}")


# ---------------------------------------------------------------------------
# describe
# ---------------------------------------------------------------------------

def _expand_members_for_describe(members: list) -> list[str]:
    """Recursively expand workflow members to an ordered list of step names."""
    from ASOkai._pipeline.base import Step, Task, Workflow
    out: list[str] = []
    for member in members:
        if isinstance(member, Workflow):
            out.extend(_expand_members_for_describe(member.members))
        elif isinstance(member, Task):
            out.extend(s.name for s in member.steps)
        elif isinstance(member, Step):
            out.append(member.name)
    return out


def _dependency_name(dep) -> str:
    """Return a registry key for dependency-like values."""
    return getattr(dep, "name", dep)


def _dependency_tree_lines(
    registry: dict,
    deps: list[str],
    prefix: str = "",
    seen: set[str] | None = None,
) -> list[str]:
    """Build recursive dependency tree lines. Avoids cycles."""
    seen = seen or set()
    lines = []
    for index, dep in enumerate(deps):
        dep_name = _dependency_name(dep)
        is_last = index == len(deps) - 1
        connector = "`-- " if is_last else "|-- "

        if dep_name in seen:
            lines.append(f"{prefix}{connector}{dep_name} (cycle)")
            continue

        lines.append(f"{prefix}{connector}{dep_name}")
        sub = registry.get(dep_name)
        if sub is None:
            continue

        subdeps = (
            getattr(sub, "dependencies", None)
            or getattr(sub, "steps", None)
            or []
        )
        child_prefix = f"{prefix}{'    ' if is_last else '|   '}"
        lines.extend(
            _dependency_tree_lines(
                registry,
                subdeps,
                child_prefix,
                seen | {dep_name},
            )
        )
    return lines


def _step_parser_actions_by_dest(step_name: str) -> dict[str, argparse.Action]:
    """Return argparse actions from a step's internal parser, keyed by dest."""
    action_by_dest: dict[str, argparse.Action] = {}
    try:
        mod = _resolve_step_module(step_name)
        build_parser = getattr(mod, "_build_parser")
        for action in build_parser()._actions:
            if action.dest != "help":
                action_by_dest[action.dest] = action
    except (KeyError, AttributeError):
        pass
    return action_by_dest


def _config_hint_for_action(action: argparse.Action | None) -> str:
    """Return a compact describe hint for a step config option."""
    if action and action.choices:
        return f"  {' | '.join(str(c) for c in action.choices)}"
    if action and action.type is int:
        return "  int"
    if action and action.help and action.help != argparse.SUPPRESS:
        return f"  {action.help}"
    return ""


def _describe_step_config_keys(step) -> None:
    """Print configurable keys for a step."""
    if not step.config_map:
        return

    action_by_dest = _step_parser_actions_by_dest(step.name)
    click.echo("Config keys :")
    for cwl_key, config_path in step.config_map.items():
        hint = _config_hint_for_action(action_by_dest.get(cwl_key))
        click.echo(f"  --config {config_path:<32}{hint}")


def _describe_step_input_overrides(step) -> None:
    """Print optional input overrides for a step."""
    input_overrides = getattr(step, "input_overrides", {})
    if not input_overrides:
        return

    click.echo("Input overrides (optional, bypasses dep step):")
    for cwl_key, config_path in input_overrides.items():
        click.echo(
            f"  --config {config_path:<32}path to file  "
            f"(replaces '{cwl_key}' from dep)"
        )


def _describe_step(step) -> tuple[list[str], str]:
    """Print step-specific details and return dependencies for summary."""
    click.echo(f"CWL         : {step.cwl_path}")
    _describe_step_config_keys(step)
    _describe_step_input_overrides(step)
    return step.dependencies or [], "Dependencies"


def _describe_task(task) -> tuple[list[str], str]:
    """Print task-specific details and return steps for summary."""
    step_names = [s.name for s in task.steps]
    click.echo(f"Steps       : {', '.join(step_names)}")
    click.echo("CWL         : (generated at runtime)")
    return step_names, "Steps"


def _describe_workflow(workflow) -> tuple[list[str], str]:
    """Print workflow-specific details and return expanded steps for summary."""
    member_names = [m.name for m in workflow.members]
    click.echo(f"Members     : {', '.join(member_names)}")
    click.echo("CWL         : (generated at runtime)")
    return _expand_members_for_describe(workflow.members), "Steps (expanded)"


def _describe_dependencies(label: str, deps: list[str], unit: str, verbose: bool) -> None:
    """Print the dependency summary for describe output."""
    if not deps:
        click.echo(f"{label}: (none)")
    elif verbose and unit == "step":
        combined = {**get_steps(), **get_tasks(), **get_workflows()}
        click.echo(f"{label}:")
        for line in _dependency_tree_lines(combined, deps):
            click.echo(f"  {line}")
    else:
        click.echo(f"{label}: {', '.join(str(d) for d in deps)}")


@main.command("describe")
@verbose_option
@click.argument("unit", type=click.Choice(["step", "task", "workflow"]))
@click.argument("name")
@click.pass_context
def describe_cmd(ctx: click.Context, unit: str, name: str) -> None:
    """Describe a step, task, or workflow."""
    registry = {
        "step": get_steps,
        "task": get_tasks,
        "workflow": get_workflows,
    }[unit]()
    obj = registry.get(name)
    if obj is None:
        raise click.ClickException(f"Unknown {unit} '{name}'.")

    click.echo(f"Name        : {obj.name}")
    click.echo(f"Description : {obj.description}")

    if unit == "step":
        deps, label = _describe_step(obj)
    elif unit == "task":
        deps, label = _describe_task(obj)
    else:
        deps, label = _describe_workflow(obj)

    verbose = ctx.obj.get("verbose", False)
    _describe_dependencies(label, deps, unit, verbose)


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------

def _flatten_config_overrides(config_overrides: tuple) -> list[str]:
    """Flatten variadic and repeated --config values."""
    flat_overrides = []
    for value in config_overrides:
        if isinstance(value, tuple):
            flat_overrides.extend(value)
        else:
            flat_overrides.append(value)
    return flat_overrides


def _flatten_option_values(values: tuple) -> list[str]:
    """Flatten variadic and repeated option values."""
    flat_values = []
    for value in values:
        if isinstance(value, tuple):
            flat_values.extend(value)
        else:
            flat_values.append(value)
    return flat_values


def _parse_run_config(config_overrides: tuple) -> dict:
    """Parse KEY=VALUE config overrides."""
    parsed_overrides = {}
    for override in _flatten_config_overrides(config_overrides):
        if "=" not in override:
            raise click.BadParameter(
                f"'{override}' is not in KEY=VALUE format.",
                param_hint="--config",
            )
        key, _, value = override.partition("=")
        parsed_overrides[key] = yaml.safe_load(value)
    return parsed_overrides


def _export_only_parent(
    config: dict,
    export_only: str | Literal[True] | None,
) -> Path | None:
    """Resolve the optional --export-only value to an export parent directory."""
    if export_only is None:
        return None
    if export_only is True:
        return Path(config["datadir"]) / "jobs"
    return Path(export_only)


def _collect_runnables(
    step_names: tuple[str, ...],
    task_names: tuple[str, ...],
    workflow_name: str | None,
) -> list:
    """Resolve CLI run selections to registered runnable objects."""
    steps_reg = get_steps()
    tasks_reg = get_tasks()
    workflows_reg = get_workflows()

    runnables = []
    for name in _flatten_option_values(step_names):
        if name not in steps_reg:
            raise click.BadParameter(f"Unknown step '{name}'.", param_hint="--steps")
        runnables.append(steps_reg[name])
    for name in _flatten_option_values(task_names):
        if name not in tasks_reg:
            raise click.BadParameter(f"Unknown task '{name}'.", param_hint="--tasks")
        runnables.append(tasks_reg[name])
    if workflow_name:
        if workflow_name not in workflows_reg:
            raise click.BadParameter(
                f"Unknown workflow '{workflow_name}'.",
                param_hint="--workflow",
            )
        runnables.append(workflows_reg[workflow_name])

    if not runnables:
        raise click.UsageError(
            "Select at least one runnable with --steps, --tasks, or --workflow."
        )
    return runnables


@main.command("run")
@verbose_option
@click.option(
    "-c", "--configfile", "--config-file",
    "config_path",
    type=click.Path(exists=True, path_type=Path),
    default=DEFAULT_CONFIG,
    show_default=True,
    help="Path to config.yaml.",
)
@click.option(
    "--steps",
    "step_names",
    cls=_VariadicOption,
    multiple=True,
    type=click.UNPROCESSED,
    metavar="NAME [NAME ...]",
    help="Step(s) to run. Repeat the flag or pass multiple names.",
)
@click.option(
    "--tasks",
    "task_names",
    cls=_VariadicOption,
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
    "--export-cwl",
    "export_cwl",
    type=click.Path(path_type=Path),
    default=None,
    metavar="PATH",
    help="Save the generated CWL for a task or workflow to PATH instead of a tempfile.",
)
@click.option(
    "--export-only",
    "export_only",
    cls=_OptionalPathOption,
    metavar="[PATH]",
    help=(
        "Export a runnable CWL bundle instead of executing. "
        "Defaults to datadir/jobs when PATH is omitted."
    ),
)
@click.option(
    "--executor",
    "executor_name",
    type=click.Choice(["toil", "cwltool"]),
    default="cwltool",
    show_default=True,
    help="CWL executor backend.",
)
@click.option(
    "--config",
    "config_overrides",
    cls=_VariadicOption,
    multiple=True,
    type=click.UNPROCESSED,
    metavar="KEY=VALUE [KEY=VALUE ...]",
    help="Override config values.",
)
@click.pass_context
def run_cmd(
    ctx: click.Context,
    config_path: Path,
    step_names: tuple[str, ...],
    task_names: tuple[str, ...],
    workflow_name: str | None,
    force: bool,
    dry_run: bool,
    recursive: bool,
    export_cwl: Path | None,
    export_only: str | Literal[True] | None,
    executor_name: str,
    config_overrides: tuple,
) -> None:
    """Run selected steps, tasks, or a workflow."""
    config = cfg.load(config_path)

    parsed_overrides = _parse_run_config(config_overrides)
    if parsed_overrides:
        cfg.apply_overrides(config, parsed_overrides)

    export_only_dir = _export_only_parent(config, export_only)
    if export_cwl is not None and export_only_dir is not None:
        raise click.UsageError("--export-only and --export-cwl are mutually exclusive.")

    runnables = _collect_runnables(step_names, task_names, workflow_name)
    executor = CwlToolExecutor() if executor_name == "cwltool" else ToilExecutor()
    runner.run_all(
        runnables,
        config,
        force=force,
        dry_run=dry_run,
        recursive=recursive,
        export_cwl=export_cwl,
        export_only=export_only_dir,
        executor=executor,
    )


# ---------------------------------------------------------------------------
# step  (hidden — called by CWL baseCommand)
# ---------------------------------------------------------------------------

def _resolve_step_cli(step_name: str) -> Callable[[list[str] | None], int]:
    """Return the CLI entrypoint for an internal step command."""
    return cast(
        Callable[[list[str] | None], int],
        getattr(_resolve_step_module(step_name), "main"),
    )


@main.command(
    "step",
    hidden=True,
    context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
)
@click.argument("step_name")
@click.pass_context
def step_cmd(ctx: click.Context, step_name: str) -> None:
    """Dispatch an internal step CLI for CWL and debugging."""
    if step_name not in get_steps():
        raise click.ClickException(f"Unknown step '{step_name}'.")

    try:
        step_main = _resolve_step_cli(step_name)
    except (AttributeError, ImportError, KeyError) as exc:
        raise click.ClickException(
            f"Step '{step_name}' does not expose an internal CLI entrypoint."
        ) from exc

    try:
        exit_code = step_main(list(ctx.args))
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 1
        raise click.exceptions.Exit(code) from exc

    if exit_code:
        raise click.exceptions.Exit(exit_code)
