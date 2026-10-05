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
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from ASOkai._pipeline.base import is_valid_runnable_name
from ASOkai._pipeline.steps.base import Step


@dataclass(frozen=True)
class FromRun:
    """Reference to a named run's declared output before planning."""

    run_id: str
    output_name: str

    def __post_init__(self) -> None:
        if (
            type(self.run_id) is not str
            or not self.run_id
            or not all(is_valid_runnable_name(part) for part in self.run_id.split("."))
        ):
            raise ValueError("Run output reference requires a valid run ID.")
        if not is_valid_runnable_name(self.output_name):
            raise ValueError("Run output reference requires a valid output name.")

    @classmethod
    def parse(cls, value: str) -> FromRun:
        """Parse ``run.ID.OUTPUT`` (including dotted task IDs)."""
        if type(value) is not str or not value.startswith("run."):
            raise ValueError("Input reference must use run.ID.OUTPUT.")
        run_id, dot, output_name = value[4:].rpartition(".")
        if not dot:
            raise ValueError("Input reference must use run.ID.OUTPUT.")
        return cls(run_id, output_name)

    def __str__(self) -> str:
        return f"run.{self.run_id}.{self.output_name}"


RunInput = Path | FromRun


def parse_run_input(value: RunInput | Mapping[str, Any]) -> RunInput:
    """Normalize a declared path or run reference into a typed source."""
    if isinstance(value, Path):
        return value.resolve()
    if isinstance(value, FromRun):
        return value
    if not isinstance(value, Mapping):
        raise TypeError("Run input must specify a path or from reference.")
    if set(value) == {"path"}:
        path = value["path"]
        if type(path) is not str or not path.strip():
            raise ValueError("Run input path must be non-blank.")
        return Path(path).resolve()
    if set(value) == {"from"}:
        return FromRun.parse(value["from"])
    raise TypeError("Run input must specify only path or from.")


@dataclass(frozen=True, init=False)
class RunSpec:
    """One selected step before configuration and input sources are resolved."""

    run_id: str
    step: Step
    parameters: Mapping[str, Any]
    inputs: Mapping[str, RunInput]
    location: str | None = field(repr=False, compare=False)

    def __init__(
        self,
        run_id: str,
        step: Step,
        parameters: Mapping[str, Any] | None = None,
        inputs: Mapping[str, RunInput | Mapping[str, Any]] | None = None,
        location: str | None = None,
    ) -> None:
        object.__setattr__(self, "run_id", run_id)
        object.__setattr__(self, "step", step)
        object.__setattr__(
            self, "parameters", parameters if parameters is not None else {}
        )
        object.__setattr__(self, "inputs", inputs if inputs is not None else {})
        object.__setattr__(self, "location", location)
        self.__post_init__()

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
        object.__setattr__(
            self,
            "inputs",
            MappingProxyType(
                {name: parse_run_input(value) for name, value in self.inputs.items()}
            ),
        )
