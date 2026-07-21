#!/usr/bin/env python
"""Translate pipeline resource configuration to CWL requirements."""

from __future__ import annotations

from typing import Any, Mapping

from ASOkai._pipeline import config as cfg


def cwl_resource_requirement(
    config: Mapping[str, Any],
    step_name: str,
    authored_requirement: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the CWL resource requirement for one pipeline step."""
    authored_requirement = authored_requirement or {}
    requirement = {
        "coresMin": authored_requirement.get(
            "coresMin",
            cfg.DEFAULT_STEP_RESOURCES[cfg.RESOURCE_N_PROCESSES_KEY],
        ),
        "ramMin": authored_requirement.get(
            "ramMin",
            cfg.DEFAULT_STEP_RESOURCES[cfg.RESOURCE_MEMORY_KEY],
        ),
    }
    configured = cfg.step_resource_overrides(config, step_name)
    if cfg.RESOURCE_N_PROCESSES_KEY in configured:
        requirement["coresMin"] = configured[cfg.RESOURCE_N_PROCESSES_KEY]
    if cfg.RESOURCE_MEMORY_KEY in configured:
        requirement["ramMin"] = configured[cfg.RESOURCE_MEMORY_KEY]
    return requirement
