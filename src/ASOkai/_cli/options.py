#!/usr/bin/env python
"""
Filename: src/ASOkai/_cli/options.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Shared options and value parsing for the ASOkai CLI.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

import logging
from pathlib import Path

import click

from ASOkai._logging import active_log_contexts, prefix_log_lines

DEFAULT_CONFIG = Path("config.yaml")
CONTEXT_SETTINGS = {"help_option_names": ["-h", "--help"]}
_NORMAL_LOG_FORMATTER = logging.Formatter("%(message)s")
_VERBOSE_LOG_FORMATTER = logging.Formatter("%(levelname)s %(name)s: %(message)s")


class _CliLogFormatter(logging.Formatter):
    """Show logger details only when debug logging is enabled."""

    def format(self, record: logging.LogRecord) -> str:
        formatter = (
            _VERBOSE_LOG_FORMATTER
            if logging.getLogger().isEnabledFor(logging.DEBUG)
            else _NORMAL_LOG_FORMATTER
        )
        return prefix_log_lines(
            active_log_contexts(),
            formatter.format(record),
        )


def configure_logging(*, verbose: bool = False) -> None:
    """Configure human-readable logging for one CLI process."""
    handler = logging.StreamHandler()
    handler.setFormatter(_CliLogFormatter())
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, handlers=[handler])
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)


def _set_verbose(
    ctx: click.Context,
    param: click.Parameter,
    value: bool,
) -> bool:
    if value:
        configure_logging(verbose=True)
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = value
    return value


verbose_option = click.option(
    "-v",
    "--verbose",
    is_flag=True,
    is_eager=True,
    expose_value=False,
    callback=_set_verbose,
    help="Enable debug logging.",
)

catalog_verbose_option = click.option(
    "-v",
    "--verbose",
    is_flag=True,
    is_eager=True,
    expose_value=False,
    callback=_set_verbose,
    help="Show internal steps and enable debug logging.",
)

describe_verbose_option = click.option(
    "-v",
    "--verbose",
    is_flag=True,
    is_eager=True,
    expose_value=False,
    callback=_set_verbose,
    help="Show configuration keys, file details, dependency trees, and internal steps.",
)
