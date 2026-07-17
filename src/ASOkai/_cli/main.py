#!/usr/bin/env python
"""
Filename: src/ASOkai/_cli/main.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Version: 0.1.1
Description: ASOkai CLI entry point.
License: LGPL-3.0-or-later
"""
from __future__ import annotations

import importlib
import logging
from itertools import groupby
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, cast

import click
import yaml

from ASOkai._pipeline import config as cfg
from ASOkai._pipeline import runner
from ASOkai._pipeline.base import (
    AnalysisStep,
    CoreStep,
)
from ASOkai._pipeline.registry import get_steps, get_tasks, get_workflows

DEFAULT_CONFIG = Path("config.yaml")
CONTEXT_SETTINGS = {"help_option_names": ["-h", "--help"]}


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


@click.group(context_settings=CONTEXT_SETTINGS)
@click.pass_context
def main(ctx: click.Context) -> None:
    """\b
            ..=#*+==-==+**-.
          :+#-.............-#=.
        :#=:.................:=#:
      .++.......................+=.
     .#-.......-*#**+**#*:.......-#.
    .*:.....-*+:::::::::::**-.....-+.
    -+....-#-:::::::::::::::-#-....+:
    *-...=*:::::::::::::::::::*-...-+
    %:..=*:::::::::+*+:::::::::#-..:*
    %:.:*:::::-+#-------%+::::::#:.:*
    *-.-+::::++-----------++::::*-.-+
    :+.-+:::++-------------*=:::*-.+:
    .+-:*::-%---------------%:::#:-+.
     .#-++:-%---------------%::#==*.
      .=++*:%--------------=#:*=*=.
        .###-#-------------*=##*.
          .=@%@*---------#@@%=.
             .-+#%*+++*%#+:.

    ASOkai — ASO design pipeline.
    """
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

def _step_category_path(step: object) -> tuple[str, ...]:
    """Return the CLI category path for a step."""
    if isinstance(step, CoreStep):
        return ("core",)
    if isinstance(step, AnalysisStep):
        return ("analysis",)
    return ("pipeline",)


def _step_type_label(step: object) -> str:
    """Return the CLI display label for a step type."""
    return " / ".join(part.capitalize() for part in _step_category_path(step))


def _analysis_scope_label(analysis_cls: type | None) -> str | None:
    """Return the analysis-scope label derived from an analysis class."""
    if analysis_cls is None:
        return None
    return getattr(analysis_cls, "scope_label", None)


def _display_description(obj: object) -> str:
    """Return CLI description text, enriching analysis steps with analysis scope."""
    description = getattr(obj, "description", "")
    if isinstance(obj, AnalysisStep):
        scope = _analysis_scope_label(getattr(obj, "analysis_cls", None))
        if scope:
            return f"[{scope}] {description}"
    return description


@main.command("list", context_settings=CONTEXT_SETTINGS)
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

    name_width = max(len(name) for name in registry) + 2

    if unit == "steps":
        category_order = {"core": 0, "analysis": 1}
        rows = sorted(
            registry.items(),
            key=lambda item: (
                category_order.get(_step_category_path(item[1])[0], 99),
                _step_category_path(item[1]),
                item[0],
            ),
        )
        for index, (category, items) in enumerate(
            groupby(rows, key=lambda item: _step_category_path(item[1]))
        ):
            if index:
                click.echo()
            click.echo(" / ".join(part.capitalize() for part in category))
            for name, obj in items:
                click.echo(f"  {name:<{name_width}} {_display_description(obj)}")
        return

    for name, obj in sorted(registry.items()):
        click.echo(f"  {name:<{name_width}} {_display_description(obj)}")


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


def _config_hint_for_param(param: Any) -> str:
    """Return a compact describe hint from StepSpec parameter metadata."""
    choices = param.parser_choices()
    if choices:
        return f"  {' | '.join(str(c) for c in choices)}"

    if param.parser_type() is int:
        return "  int"

    doc = getattr(param, "doc", None)
    if doc:
        return f"  {doc}"
    return ""


def _describe_step_config_keys(step) -> None:
    """Print configurable keys for a step."""
    config_params = [
        param
        for param in (*step.spec.params, *step.spec.inputs)
        if param.cwl and param.config
    ]
    if not config_params:
        return

    click.echo("Config keys :")
    for param in config_params:
        hint = _config_hint_for_param(param)
        click.echo(f"  --config {param.config:<32}{hint}")


def _describe_step_input_overrides(step) -> None:
    """Print optional input overrides for a step."""
    input_overrides = step.input_overrides
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
    click.echo(f"Type        : {_step_type_label(step)}")
    _describe_step_config_keys(step)
    _describe_step_input_overrides(step)
    return step.dependencies or [], "Dependencies"


def _describe_task(task) -> tuple[list[str], str]:
    """Print task-specific details and return steps for summary."""
    step_names = [s.name for s in task.steps]
    click.echo(f"Steps       : {', '.join(step_names)}")
    click.echo("CWL         : (CLI collection; export creates run.cwl)")
    return step_names, "Steps"


def _describe_workflow(workflow) -> tuple[list[str], str]:
    """Print workflow-specific details and return expanded steps for summary."""
    member_names = [m.name for m in workflow.members]
    click.echo(f"Members     : {', '.join(member_names)}")
    click.echo("CWL         : (CLI collection; export creates run.cwl)")
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


@main.command("describe", context_settings=CONTEXT_SETTINGS)
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
    click.echo(f"Description : {_display_description(obj)}")

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


@main.command("run", context_settings=CONTEXT_SETTINGS)
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
    executor_name: str,
    config_overrides: tuple,
) -> None:
    """Run selected steps, tasks, or a workflow."""
    config = cfg.load(config_path)

    parsed_overrides = _parse_run_config(config_overrides)
    if parsed_overrides:
        cfg.apply_overrides(config, parsed_overrides)

    runnables = _collect_runnables(step_names, task_names, workflow_name)
    executor = runner.executor_from_name(executor_name)
    runner.run_all(
        runnables,
        config,
        force=force,
        dry_run=dry_run,
        recursive=recursive,
        executor=executor,
    )


# ---------------------------------------------------------------------------
# export
# ---------------------------------------------------------------------------

@main.command("export", context_settings=CONTEXT_SETTINGS)
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
    help="Step(s) to export. Repeat the flag or pass multiple names.",
)
@click.option(
    "--tasks",
    "task_names",
    cls=_VariadicOption,
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
    "outdir",
    type=click.Path(path_type=Path),
    default=None,
    metavar="DIR",
    help="Directory under which to write the export bundle. Defaults to datadir/jobs.",
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
    cls=_VariadicOption,
    multiple=True,
    type=click.UNPROCESSED,
    metavar="KEY=VALUE [KEY=VALUE ...]",
    help="Override config values.",
)
def export_cmd(
    config_path: Path,
    step_names: tuple[str, ...],
    task_names: tuple[str, ...],
    workflow_name: str | None,
    recursive: bool,
    outdir: Path | None,
    executor_name: str,
    config_overrides: tuple,
) -> None:
    """Export selected steps, tasks, or a workflow as a runnable CWL bundle."""
    config = cfg.load(config_path)

    parsed_overrides = _parse_run_config(config_overrides)
    if parsed_overrides:
        cfg.apply_overrides(config, parsed_overrides)

    runnables = _collect_runnables(step_names, task_names, workflow_name)
    try:
        export_dir = runner.export_all(
            runnables,
            config,
            recursive=recursive,
            outdir=outdir,
            runner_name=runner.runner_name_from_name(executor_name),
        )
    except RuntimeError as exc:
        raise click.ClickException(str(exc)) from exc

    click.echo(f"CWL export bundle written to {export_dir}")


# ---------------------------------------------------------------------------
# Internal CWL commands
# ---------------------------------------------------------------------------

@main.command("publish-outputs", hidden=True)
@click.argument(
    "manifest",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)
@click.argument(
    "sources",
    nargs=-1,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)
def publish_outputs_cmd(manifest: Path, sources: tuple[Path, ...]) -> None:
    """Publish CWL output files into their declared data hierarchy."""
    from ASOkai._cwl.publisher import publish_outputs

    try:
        publish_outputs(manifest, sources)
    except (OSError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc


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
