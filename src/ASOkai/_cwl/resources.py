#!/usr/bin/env python
"""
Filename: src/ASOkai/_cwl/resources.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Translate pipeline resource configuration to CWL requirements.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

from typing import Any, Mapping

from ASOkai._pipeline import config as cfg
from ASOkai._pipeline.steps.base import Step


def cwl_resource_requirement(
    config: Mapping[str, Any],
    step: Step,
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
    configured = cfg.step_resource_overrides(config, step.name)
    if step.supports_multiple_processes:
        requirement["coresMin"] = cfg.step_resources(config, step)[
            cfg.RESOURCE_N_PROCESSES_KEY
        ]
    if cfg.RESOURCE_MEMORY_KEY in configured:
        requirement["ramMin"] = configured[cfg.RESOURCE_MEMORY_KEY]
    return requirement
