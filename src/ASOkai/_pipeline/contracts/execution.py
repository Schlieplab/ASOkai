#!/usr/bin/env python
"""
Filename: src/ASOkai/_pipeline/contracts/execution.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Version: 0.1.1
Description: Immutable contracts for concrete step runs and execution plans.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from ASOkai._pipeline.contracts.files import FileInput, FileOutput
from ASOkai._pipeline.steps.base import Step


@dataclass(frozen=True, eq=False)
class StepRun:
    """One concrete execution of a step under resolved configuration."""

    run_id: str
    step: Step
    config: Mapping[str, Any] = field(repr=False)
    inputs: tuple[StepInputBinding, ...] = ()

    def __post_init__(self) -> None:
        if type(self.run_id) is not str or not self.run_id.strip():
            raise ValueError("StepRun.run_id must be a non-blank string.")
        if not isinstance(self.step, Step):
            raise TypeError("StepRun.step must be a Step.")
        if not isinstance(self.config, Mapping):
            raise TypeError("StepRun.config must be a mapping.")

        inputs = tuple(self.inputs)
        if any(not isinstance(item, StepInputBinding) for item in inputs):
            raise TypeError(
                "StepRun.inputs must contain only StepInputBinding values."
            )
        input_names = [item.file_input.name for item in inputs]
        duplicates = sorted(
            {name for name in input_names if input_names.count(name) > 1}
        )
        if duplicates:
            raise ValueError(
                "StepRun input bindings contain duplicate name(s): "
                f"{', '.join(duplicates)}."
            )

        object.__setattr__(
            self,
            "config",
            MappingProxyType(deepcopy(dict(self.config))),
        )
        object.__setattr__(self, "inputs", inputs)

    def __eq__(self, other: object) -> bool:
        """Concrete runs compare by their stable resolved identity."""
        return isinstance(other, StepRun) and self.run_id == other.run_id

    def __hash__(self) -> int:
        return hash(self.run_id)

    def output(self, output: FileOutput) -> StepRunOutput:
        """Return one output port qualified by this concrete run."""
        try:
            declared = self.step.spec.output(output.name)
        except KeyError as error:
            raise ValueError(
                f"Output '{output.name}' does not belong to step "
                f"'{self.step.name}'."
            ) from error
        if declared is not output:
            raise ValueError(
                f"Output '{output.name}' does not belong to step "
                f"'{self.step.name}'."
            )
        return StepRunOutput(self, output)


@dataclass(frozen=True)
class StepRunOutput:
    """One declared file output produced by one concrete step run."""

    run: StepRun
    output: FileOutput

    def __post_init__(self) -> None:
        if not isinstance(self.run, StepRun):
            raise TypeError("StepRunOutput.run must be a StepRun.")
        if not isinstance(self.output, FileOutput):
            raise TypeError("StepRunOutput.output must be a FileOutput.")


@dataclass(frozen=True)
class StepInputBinding:
    """A step input resolved to an external path or producer-run output."""

    file_input: FileInput
    source: Path | StepRunOutput

    def __post_init__(self) -> None:
        if not isinstance(self.file_input, FileInput):
            raise TypeError("StepInputBinding.file_input must be a FileInput.")
        if isinstance(self.source, Path):
            object.__setattr__(self, "source", self.source.resolve())
        elif not isinstance(self.source, StepRunOutput):
            raise TypeError(
                "StepInputBinding.source must be a Path or StepRunOutput."
            )


@dataclass(frozen=True)
class ExecutionPlan:
    """Resolved goals, scheduled runs, and reusable run outputs."""

    goals: tuple[StepRun, ...]
    runs_to_execute: tuple[StepRun, ...]
    resolved_outputs: Mapping[StepRunOutput, Path] = field(default_factory=dict)

    def __post_init__(self) -> None:
        goals = tuple(self.goals)
        runs_to_execute = tuple(self.runs_to_execute)
        if any(not isinstance(run, StepRun) for run in goals):
            raise TypeError("ExecutionPlan.goals must contain only StepRun values.")
        if any(not isinstance(run, StepRun) for run in runs_to_execute):
            raise TypeError(
                "ExecutionPlan.runs_to_execute must contain only StepRun values."
            )

        resolved_outputs: dict[StepRunOutput, Path] = {}
        for output, path in self.resolved_outputs.items():
            if not isinstance(output, StepRunOutput):
                raise TypeError(
                    "ExecutionPlan.resolved_outputs keys must be StepRunOutput "
                    "values."
                )
            if not isinstance(path, Path):
                raise TypeError(
                    "ExecutionPlan.resolved_outputs values must be Path values."
                )
            resolved_outputs[output] = path.resolve()

        object.__setattr__(self, "goals", goals)
        object.__setattr__(self, "runs_to_execute", runs_to_execute)
        object.__setattr__(
            self,
            "resolved_outputs",
            MappingProxyType(resolved_outputs),
        )
