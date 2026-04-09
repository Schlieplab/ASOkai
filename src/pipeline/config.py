"""
Filename: src/ASOkai/pipeline/config.py
Description: Config loading and resolution utilities.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


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
