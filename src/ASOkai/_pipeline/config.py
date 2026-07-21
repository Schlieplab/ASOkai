#!/usr/bin/env python
"""
Filename: src/ASOkai/_pipeline/config.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Version: 0.1.1
Description: Config loading and resolution utilities.
License: LGPL-3.0-or-later
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import yaml


RESOURCE_N_PROCESSES_KEY = "n_processes"
RESOURCE_MEMORY_KEY = "memory_mb"
RESOURCE_DEFAULT_KEY = "default"
DEFAULT_STEP_RESOURCES = {
    RESOURCE_N_PROCESSES_KEY: 1,
    RESOURCE_MEMORY_KEY: 4096,
}
SUPPORTED_RESOURCE_KEYS = frozenset(DEFAULT_STEP_RESOURCES)


def load(path: Path | str) -> dict:
    """Load config.yaml from disk."""
    with open(path) as f:
        return yaml.safe_load(f)


def resolve(config: dict, dotted_key: str) -> Any:
    """
    Resolve a dotted key against a config dict.

    Example:
        resolve(config, "genome.assembly_id")  →  config["genome"]["assembly_id"]
    """
    value = config
    for key in dotted_key.split("."):
        try:
            value = value[key]
        except KeyError:
            raise KeyError(f"Config key '{dotted_key}' not found (missing '{key}').")
    return value


def apply_overrides(config: dict, overrides: dict[str, Any]) -> dict:
    """
    Apply CLI overrides to config in-place.

    Overrides use dotted keys, e.g.:
        {"genome.ensembl_release": 115}  →  config["genome"]["ensembl_release"] = 115
    """
    for dotted_key, value in overrides.items():
        keys = dotted_key.split(".")
        target = config
        for key in keys[:-1]:
            target = target.setdefault(key, {})
        target[keys[-1]] = value
    return config


def step_resources(config: Mapping[str, Any], step_name: str) -> dict[str, Any]:
    """Return resolved resource settings for one step."""
    return {
        **DEFAULT_STEP_RESOURCES,
        **step_resource_overrides(config, step_name),
    }


def step_resource_overrides(
    config: Mapping[str, Any],
    step_name: str,
) -> dict[str, Any]:
    """Return configured values for one step without built-in defaults."""
    all_resources = config.get("resources", {})
    if all_resources is None:
        return {}
    if not isinstance(all_resources, Mapping):
        raise TypeError("Config key 'resources' must be a mapping of step names.")

    configured_defaults = all_resources.get(RESOURCE_DEFAULT_KEY, {})
    if configured_defaults is None:
        configured_defaults = {}
    if not isinstance(configured_defaults, Mapping):
        raise TypeError(
            f"Config key 'resources.{RESOURCE_DEFAULT_KEY}' must be a mapping."
        )

    step_overrides = all_resources.get(step_name, {})
    if step_overrides is None:
        step_overrides = {}
    if not isinstance(step_overrides, Mapping):
        raise TypeError(f"Config key 'resources.{step_name}' must be a mapping.")

    _validate_resource_values(
        configured_defaults,
        f"resources.{RESOURCE_DEFAULT_KEY}",
    )
    _validate_resource_values(step_overrides, f"resources.{step_name}")
    return {**configured_defaults, **step_overrides}


def _validate_resource_values(resources: Mapping[str, Any], path: str) -> None:
    """Validate the resource fields currently understood by ASOkai."""
    unsupported = set(resources) - SUPPORTED_RESOURCE_KEYS
    if unsupported:
        names = ", ".join(sorted(unsupported))
        raise ValueError(f"Unsupported resource key(s) at '{path}': {names}.")

    for key in SUPPORTED_RESOURCE_KEYS:
        if key not in resources:
            continue
        value = resources[key]
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError(
                f"Config key '{path}.{key}' must be a positive integer."
            )
