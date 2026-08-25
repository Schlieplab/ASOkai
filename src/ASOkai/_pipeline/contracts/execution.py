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
import re
from types import MappingProxyType
from typing import Any, Mapping

from ASOkai._pipeline.contracts.files import FileInput, FileOutput
from ASOkai._pipeline.steps.base import Step


_RUN_ID_PATTERN = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9_-]*(?:\.[A-Za-z0-9][A-Za-z0-9_-]*)*"
)


@dataclass(frozen=True, eq=False)
class StepRun:
    """One concrete execution of a step under resolved configuration."""

    run_id: str
    step: Step
    config: Mapping[str, Any] = field(repr=False)
    inputs: tuple[StepInputBinding, ...] = ()

    def __post_init__(self) -> None:
        if (
            type(self.run_id) is not str
            or _RUN_ID_PATTERN.fullmatch(self.run_id) is None
        ):
            raise ValueError(
                "StepRun.run_id must contain dot-separated names using only "
                "letters, numbers, hyphens, and underscores."
            )
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

        declared_inputs = {
            file_input.name: file_input
            for file_input in self.step.spec.inputs
        }
        bound_inputs = {
            binding.file_input.name: binding.file_input
            for binding in inputs
        }
        if declared_inputs.keys() != bound_inputs.keys():
            missing = ", ".join(
                sorted(declared_inputs.keys() - bound_inputs.keys())
            ) or "none"
            unexpected = ", ".join(
                sorted(bound_inputs.keys() - declared_inputs.keys())
            ) or "none"
            raise ValueError(
                f"StepRun '{self.run_id}' input bindings do not match step "
                f"'{self.step.name}' (missing: {missing}; "
                f"unexpected: {unexpected})."
            )
        for name, file_input in bound_inputs.items():
            if file_input is not declared_inputs[name]:
                raise ValueError(
                    f"StepRun '{self.run_id}' input binding '{name}' does not "
                    f"use the declaration from step '{self.step.name}'."
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
        try:
            declared_output = self.run.step.spec.output(self.output.name)
        except KeyError as error:
            raise ValueError(
                f"Output '{self.output.name}' does not belong to step "
                f"'{self.run.step.name}'."
            ) from error
        if declared_output is not self.output:
            raise ValueError(
                f"Output '{self.output.name}' does not belong to step "
                f"'{self.run.step.name}'."
            )

    @property
    def qualified_name(self) -> str:
        """Return the output name qualified by its concrete run."""
        return f"{self.run.run_id}.{self.output.name}"


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
        elif isinstance(self.source, StepRunOutput):
            if self.source.output is not self.file_input.source:
                raise ValueError(
                    f"Input '{self.file_input.name}' requires output "
                    f"'{self.file_input.source.producer}."
                    f"{self.file_input.source.name}', but received "
                    f"'{self.source.qualified_name}'."
                )
        else:
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
