#!/usr/bin/env python
"""
Filename: src/ASOkai/_cli/options.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Version: 0.1.1
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


class VariadicOption(click.Option):
    """A Click option that consumes values until the next option."""

    def add_to_parser(self, parser, ctx):
        retval = super().add_to_parser(parser, ctx)
        for name in self.opts:
            option_parser = (
                parser._long_opt.get(name)
                or parser._short_opt.get(name)
            )
            if option_parser is None:
                continue

            previous_process = option_parser.process

            def parser_process(
                value,
                state,
                previous_process=previous_process,
            ):
                values = [value]
                while state.rargs:
                    next_arg = state.rargs[0]
                    if next_arg.startswith("-"):
                        break
                    values.append(state.rargs.pop(0))
                previous_process(tuple(values), state)

            option_parser.process = parser_process
        return retval


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


def flatten_option_values(values: tuple) -> list[str]:
    """Flatten repeated options that may each contain multiple values."""
    flattened_values = []
    for value in values:
        if isinstance(value, tuple):
            flattened_values.extend(value)
        else:
            flattened_values.append(value)
    return flattened_values


def parse_config_overrides(config_overrides: tuple) -> dict:
    """Parse repeated KEY=VALUE configuration overrides."""
    parsed_overrides = {}
    for override in flatten_option_values(config_overrides):
        if "=" not in override:
            raise click.BadParameter(
                f"'{override}' is not in KEY=VALUE format.",
                param_hint="--config",
            )
        key, _, value = override.partition("=")
        parsed_overrides[key] = yaml.safe_load(value)
    return parsed_overrides
