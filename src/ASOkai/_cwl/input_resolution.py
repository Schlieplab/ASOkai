#!/usr/bin/env python
"""
Filename: src/ASOkai/_cwl/input_resolution.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Resolve concrete step-run inputs for CWL execution.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import AbstractSet, Any, Literal

from ASOkai._pipeline.contracts.execution import StepRun, StepRunOutput


InputSource = Literal[
    "scalar",
    "dep_wired",
    "dep_disk",
    "input_override",
]


@dataclass
class ResolvedInput:
    """A CWL input value together with how ASOkai resolved it."""

    cwl_value: Any
    source: InputSource
    path: Path | None = None
    producer_output: StepRunOutput | None = None
    config_path: str | None = None


def resolve_run_inputs(
    run: StepRun,
    *,
    resolved_outputs: Mapping[StepRunOutput, Path] | None = None,
    runs_to_execute: AbstractSet[StepRun] | None = None,
) -> dict[str, ResolvedInput]:
    """Resolve every scalar and file input for one concrete step run."""
    if resolved_outputs is None:
        resolved_outputs = {}
    if runs_to_execute is None:
        runs_to_execute = set()

    resolved: dict[str, ResolvedInput] = {}
    parameter_values = run.step.resolved_parameter_values(run.config)
    for parameter in run.step.spec.params:
        if parameter.config is None:
            continue
        if parameter.name not in parameter_values:
            continue
        resolved[parameter.name] = ResolvedInput(
            cwl_value=parameter_values[parameter.name],
            source="scalar",
            config_path=parameter.config,
        )

    bindings = {binding.file_input.name: binding for binding in run.inputs}
    for file_input in run.step.spec.inputs:
        binding = bindings[file_input.name]
        source = binding.source
        if isinstance(source, Path):
            resolved[file_input.name] = ResolvedInput(
                cwl_value={"class": file_input.file_type.cwl_type, "path": str(source)},
                source="input_override",
                path=source,
                config_path=(
                    f"{file_input.configuration_path(run.step.name)}"
                    ".path_override"
                ),
            )
            continue

        producer_run = source.run
        if producer_run in runs_to_execute:
            resolved[file_input.name] = ResolvedInput(
                cwl_value=None,
                source="dep_wired",
                producer_output=source,
            )
            continue

        path = resolved_outputs.get(source)
        if path is None:
            raise RuntimeError(
                f"Run '{run.run_id}' input '{file_input.name}' requires "
                f"resolved output '{source.qualified_name}'."
            )
        resolved[file_input.name] = ResolvedInput(
            cwl_value={"class": file_input.file_type.cwl_type, "path": str(path)},
            source="dep_disk",
            path=path,
            producer_output=source,
        )

    return resolved


def to_cwl_inputs(resolved: dict[str, ResolvedInput]) -> dict[str, Any]:
    """Strip resolution metadata and exclude internally wired values."""
    return {
        name: item.cwl_value
        for name, item in resolved.items()
        if item.cwl_value is not None
    }


def workflow_input_id(run: StepRun, input_name: str) -> str:
    """Qualify a top-level CWL input by its concrete run."""
    return f"{run.run_id}.{input_name}"


def workflow_file_input_id(
    consumer_run: StepRun,
    input_name: str,
    source: Path | StepRunOutput,
) -> str:
    """Identify a top-level file input by its override or producer output."""
    if isinstance(source, StepRunOutput):
        return source.qualified_name
    return workflow_input_id(consumer_run, input_name)


def resolve_run_sequence_inputs(
    runs: Sequence[StepRun],
    resolved_outputs: Mapping[StepRunOutput, Path],
) -> dict[str, Any]:
    """Collect top-level inputs for a generated multi-run CWL workflow."""
    runs_to_execute = set(runs)
    workflow_inputs: dict[str, Any] = {}
    for run in runs:
        resolved = resolve_run_inputs(
            run,
            resolved_outputs=resolved_outputs,
            runs_to_execute=runs_to_execute,
        )
        for input_name, item in resolved.items():
            if item.cwl_value is None:
                continue
            if item.source == "scalar":
                input_id = workflow_input_id(run, input_name)
            else:
                file_source = (
                    item.producer_output
                    if item.producer_output is not None
                    else item.path
                )
                assert file_source is not None
                input_id = workflow_file_input_id(
                    run,
                    input_name,
                    file_source,
                )
            workflow_inputs[input_id] = item.cwl_value
    return workflow_inputs
