#!/usr/bin/env python
"""
Filename: src/ASOkai/_cli/main.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: ASOkai CLI entry point.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

from pathlib import Path

import click

from ASOkai._logging import log_context
from ASOkai._pipeline.catalog import get_steps

from .catalog import describe_command, list_command
from .execution import export_command, run_command
from .options import CONTEXT_SETTINGS, configure_logging


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
    configure_logging()
    ctx.ensure_object(dict)


main.add_command(list_command)
main.add_command(describe_command)
main.add_command(run_command)
main.add_command(export_command)

# ---------------------------------------------------------------------------
# Internal CWL commands
# ---------------------------------------------------------------------------


@main.command("publish-outputs", hidden=True)
@click.argument(
    "manifest",
    type=click.Path(
        exists=True,
        dir_okay=False,
        path_type=Path,
    ),
)
@click.argument(
    "sources",
    nargs=-1,
    type=click.Path(
        exists=True,
        dir_okay=False,
        path_type=Path,
    ),
)
def publish_outputs_command(
    manifest: Path,
    sources: tuple[Path, ...],
) -> None:
    """Publish CWL output files into their declared data hierarchy."""
    from ASOkai._cwl.publisher import publish_outputs

    try:
        publish_outputs(manifest, sources)
    except (OSError, ValueError) as error:
        raise click.ClickException(str(error)) from error


@main.command(
    "step",
    hidden=True,
    context_settings={
        "ignore_unknown_options": True,
        "allow_extra_args": True,
    },
)
@click.argument("step_name")
@click.pass_context
def step_command(
    ctx: click.Context,
    step_name: str,
) -> None:
    """Dispatch an internal step CLI for CWL and debugging."""
    try:
        step = get_steps().get(step_name)
    except ValueError as error:
        raise click.ClickException(str(error)) from error
    if step is None:
        raise click.ClickException(f"Unknown step '{step_name}'.")

    with log_context(f"step:{step.name}"):
        try:
            exit_code = step.run_cli(list(ctx.args))
        except SystemExit as error:
            code = error.code if isinstance(error.code, int) else 1
            raise click.exceptions.Exit(code) from error

    if exit_code:
        raise click.exceptions.Exit(exit_code)
