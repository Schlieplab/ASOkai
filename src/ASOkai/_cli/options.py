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
import yaml


DEFAULT_CONFIG = Path("config.yaml")
CONTEXT_SETTINGS = {"help_option_names": ["-h", "--help"]}


def _set_verbose(
    ctx: click.Context,
    param: click.Parameter,
    value: bool,
) -> bool:
    if value:
        logging.getLogger().setLevel(logging.DEBUG)
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


def parse_config_overrides(
    config_overrides: tuple[str, ...],
) -> dict[str, object]:
    """Parse repeated KEY=VALUE configuration overrides."""
    parsed_overrides: dict[str, object] = {}
    for override in config_overrides:
        if "=" not in override:
            raise click.BadParameter(
                f"'{override}' is not in KEY=VALUE format.",
                param_hint="--config",
            )
        key, _, value = override.partition("=")
        try:
            parsed_overrides[key] = yaml.safe_load(value)
        except yaml.YAMLError as error:
            raise click.BadParameter(
                f"'{override}' contains an invalid YAML value: {error}",
                param_hint="--config",
            ) from error
    return parsed_overrides
