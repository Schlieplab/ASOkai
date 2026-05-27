"""
Helpers for reading packaged CWL metadata.
"""

from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
from typing import Any

import yaml


@lru_cache(maxsize=None)
def load_cwl(path: str) -> dict[str, Any]:
    """Load a CWL document from disk."""
    with open(path, encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def step_input_types(cwl_path: str) -> dict[str, Any]:
    """Return a mapping of input id to CWL type for a CommandLineTool."""
    inputs = load_cwl(cwl_path).get("inputs", {})
    return {key: deepcopy(value["type"]) for key, value in inputs.items()}


def step_input_names(cwl_path: str) -> set[str]:
    """Return input ids declared by a CommandLineTool."""
    return set(load_cwl(cwl_path).get("inputs", {}))
