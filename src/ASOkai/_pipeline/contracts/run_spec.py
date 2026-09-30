#!/usr/bin/env python
"""
Filename: src/ASOkai/_pipeline/contracts/run_spec.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Unresolved declarations for selected pipeline step runs.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping

from ASOkai._pipeline.base import is_valid_runnable_name
from ASOkai._pipeline.steps.base import Step


@dataclass(frozen=True)
class RunSpec:
    """One selected step before configuration and input sources are resolved."""

    run_id: str
    step: Step
    parameters: Mapping[str, Any] = field(default_factory=dict)
    inputs: Mapping[str, Any] = field(default_factory=dict)
    location: str | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if type(self.run_id) is not str or not all(
            is_valid_runnable_name(part) for part in self.run_id.split(".")
        ):
            raise ValueError("RunSpec.run_id must contain valid dot-separated names.")
        if not isinstance(self.step, Step):
            raise TypeError("RunSpec.step must be a Step.")
        if not isinstance(self.parameters, Mapping):
            raise TypeError("RunSpec.parameters must be a mapping.")
        if not isinstance(self.inputs, Mapping):
            raise TypeError("RunSpec.inputs must be a mapping.")
        if self.location is not None and (
            type(self.location) is not str or not self.location.strip()
        ):
            raise ValueError("RunSpec.location must be non-blank when supplied.")
        object.__setattr__(self, "parameters", MappingProxyType(dict(self.parameters)))
        object.__setattr__(self, "inputs", MappingProxyType(dict(self.inputs)))
