#!/usr/bin/env python
"""
Filename: src/ASOkai/_cwl/input_resolution.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Version: 0.1.1
Description: Resolve concrete step-run inputs for CWL execution.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

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
    resolved_outputs: dict[StepRunOutput, Path] | None = None,
    run_ids_to_execute: set[str] | None = None,
) -> dict[str, ResolvedInput]:
    """Resolve every scalar and file input for one concrete step run."""
    if resolved_outputs is None:
        resolved_outputs = {}
    if run_ids_to_execute is None:
        run_ids_to_execute = set()

    resolved: dict[str, ResolvedInput] = {}
    parameter_values = run.step.resolved_parameter_values(run.config)
    for parameter in run.step.spec.params:
        if not parameter.cwl or parameter.config is None:
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
        try:
            binding = bindings[file_input.name]
        except KeyError as error:
            raise ValueError(
                f"Run '{run.run_id}' has no binding for input "
                f"'{file_input.name}'."
            ) from error

        source = binding.source
        if isinstance(source, Path):
            resolved[file_input.name] = ResolvedInput(
                cwl_value={"class": "File", "path": str(source)},
                source="input_override",
                path=source,
                config_path=(
                    f"{file_input.configuration_path(run.step.name)}"
                    ".path_override"
                ),
            )
            continue

        producer_run = source.run
        if producer_run.run_id in run_ids_to_execute:
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
            cwl_value={"class": "File", "path": str(path)},
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


def resolve_run_sequence_inputs(
    runs: list[StepRun] | tuple[StepRun, ...],
    resolved_outputs: dict[StepRunOutput, Path],
) -> dict[str, Any]:
    """Collect top-level inputs for a generated multi-run CWL workflow."""
    run_ids_to_execute = {run.run_id for run in runs}
    workflow_inputs: dict[str, Any] = {}
    for run in runs:
        resolved = resolve_run_inputs(
            run,
            resolved_outputs=resolved_outputs,
            run_ids_to_execute=run_ids_to_execute,
        )
        for input_name, item in resolved.items():
            if item.cwl_value is None:
                continue
            workflow_inputs[workflow_input_id(run, input_name)] = item.cwl_value
    return workflow_inputs
