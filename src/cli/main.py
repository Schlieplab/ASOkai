"""
Filename: src/ASOkai/cli/main.py
Description: ASOkai CLI entry point.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

import logging
from pathlib import Path

import click
import yaml

from pipeline import config as cfg
from pipeline import runner
from pipeline.registry import get_steps, get_tasks, get_workflows

DEFAULT_CONFIG = Path("config.yaml")


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


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------

@main.command("list")
@verbose_option
@click.argument("unit", type=click.Choice(["steps", "tasks", "workflows"]))
def list_cmd(unit: str) -> None:
    """List available steps, tasks, or workflows."""
    registry = {"steps": get_steps, "tasks": get_tasks, "workflows": get_workflows}[unit]()
    if not registry:
        click.echo(f"No {unit} available.")
        return
    for name, obj in sorted(registry.items()):
        click.echo(f"  {name:<35} {obj.description}")


# ---------------------------------------------------------------------------
# describe
# ---------------------------------------------------------------------------

def _dependency_tree(registry: dict, deps: list[str], depth: int = 0, seen: set | None = None) -> list[tuple[int, str]]:
    """Build recursive (depth, name) list for dependency tree. Avoids cycles."""
    seen = seen or set()
    result = []
    for dep in deps:
        if dep in seen:
            result.append((depth, f"{dep} (cycle)"))
            continue
        seen.add(dep)
        result.append((depth, dep))
        sub = registry.get(dep)
        if sub is not None:
            subdeps = getattr(sub, "dependencies", None) or []
            result.extend(_dependency_tree(registry, subdeps, depth + 1, seen))
    return result


@main.command()
@verbose_option
@click.argument("unit", type=click.Choice(["step", "task", "workflow"]))
@click.argument("name")
@click.pass_context
def describe(ctx: click.Context, unit: str, name: str) -> None:
    """Describe a step, task, or workflow."""
    registry = {"step": get_steps, "task": get_tasks, "workflow": get_workflows}[unit]()
    obj = registry.get(name)
    if obj is None:
        raise click.ClickException(f"Unknown {unit} '{name}'.")
    click.echo(f"Name        : {obj.name}")
    click.echo(f"Description : {obj.description}")
    click.echo(f"CWL         : {obj.cwl_path}")
    deps = obj.dependencies or []
    verbose = ctx.obj.get("verbose", False)
    if not deps:
        click.echo("Dependencies: (none)")
    elif verbose:
        # Combined registry for cross-type resolution (e.g. task -> step)
        combined = {**get_steps(), **get_tasks(), **get_workflows()}
        tree = _dependency_tree(combined, deps)
        click.echo("Dependencies:")
        for depth, dep_name in tree:
            click.echo(f"  {'  ' * depth}{dep_name}")
    else:
        click.echo(f"Dependencies: {', '.join(deps)}")


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------

@main.command()
@verbose_option
@click.option(
    "-c", "--config",
    "config_path",
    type=click.Path(exists=True, path_type=Path),
    default=DEFAULT_CONFIG,
    show_default=True,
    help="Path to config.yaml.",
)
@click.option("--steps",     "step_names",     multiple=True, metavar="NAME", help="Step(s) to run.")
@click.option("--tasks",     "task_names",     multiple=True, metavar="NAME", help="Task(s) to run.")
@click.option("--workflow",  "workflow_name",  default=None,  metavar="NAME", help="Workflow to run.")
@click.option("--force",     is_flag=True, help="Re-run even if outputs already exist.")
@click.option("--dry-run",   is_flag=True, help="Show what would run without executing.")
@click.option("--recursive", is_flag=True, help="Automatically run missing dependencies.")
@click.option(
    "--set", "overrides",
    multiple=True,
    metavar="KEY=VALUE",
    help="Override config values (e.g. --set genome.ensembl_release=115).",
)
@click.pass_context
def run(
    ctx: click.Context,
    config_path: Path,
    step_names: tuple[str, ...],
    task_names: tuple[str, ...],
    workflow_name: str | None,
    force: bool,
    dry_run: bool,
    recursive: bool,
    overrides: tuple[str, ...],
) -> None:
    """Run steps, tasks, or a workflow. Defaults to the 'standard' workflow."""
    config = cfg.load(config_path)

    # apply --set overrides
    parsed_overrides = {}
    for override in overrides:
        if "=" not in override:
            raise click.BadParameter(f"'{override}' is not in KEY=VALUE format.", param_hint="--set")
        key, _, value = override.partition("=")
        parsed_overrides[key] = yaml.safe_load(value)
    if parsed_overrides:
        cfg.apply_overrides(config, parsed_overrides)

    if not step_names and not task_names and not workflow_name:
        workflow_name = "standard"

    kwargs = dict(force=force, dry_run=dry_run, recursive=recursive)

    for name in step_names:
        runner.run_step(name, config, **kwargs)

    for name in task_names:
        runner.run_task(name, config, **kwargs)

    if workflow_name:
        runner.run_workflow(workflow_name, config, **kwargs)
