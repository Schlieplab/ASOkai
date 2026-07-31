#!/usr/bin/env python
"""
Filename: src/ASOkai/_cwl/input_resolution.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Version: 0.1.1
Description: Resolve step config, dependency, override, and output inputs for CWL execution.
License: LGPL-3.0-or-later
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from ASOkai._pipeline import config as cfg
from ASOkai._pipeline.contracts.files import FileOutput
from ASOkai._pipeline.steps.base import Step
from ASOkai.Plugins._registry import get_steps


InputSource = Literal[
    "scalar",
    "dep_wired",
    "dep_disk",
    "input_override",
]


@dataclass
class ResolvedInput:
    """
    An input value annotated with its resolution source.

    ``cwl_value`` is what gets passed to the executor. It is ``None`` for inputs
    that are wired internally between steps in a generated CWL job and
    therefore do not appear in the top-level inputs JSON.
    """

    cwl_value: Any
    source: InputSource
    path: Path | None = None
    dep_name: str | None = None
    source_output: FileOutput | None = None
    config_path: str | None = None


def resolve_step_inputs(
    step: Step,
    config: dict,
    *,
    pre_resolved: dict[FileOutput, Path] | None = None,
    steps_in_plan: set[str] | None = None,
    step_registry: dict[str, Step] | None = None,
) -> dict[str, ResolvedInput]:
    """
    Resolve all inputs for *step* and return them annotated with their source.

    Priority, highest first:
    1. input_overrides when the config dot-path is present.
    2. dependency outputs, either internally wired or passed as File inputs.
    3. scalar config_map values.
    """
    if pre_resolved is None:
        pre_resolved = {}
    if steps_in_plan is None:
        steps_in_plan = set()

    resolved: dict[str, ResolvedInput] = {}
    for parameter in step.spec.params:
        if not parameter.cwl or parameter.config is None:
            continue
        try:
            resolved[parameter.name] = ResolvedInput(
                cwl_value=cfg.resolve_parameter_value(
                    config,
                    parameter,
                ),
                source="scalar",
                config_path=parameter.config,
            )
        except KeyError:
            pass

    registry = step_registry
    for file_input in step.spec.inputs:
        override_path = file_input.configured_override_path(config)
        if override_path is not None:
            resolved[file_input.name] = ResolvedInput(
                cwl_value={
                    "class": "File",
                    "path": str(override_path),
                },
                source="input_override",
                path=override_path,
                config_path=file_input.override,
            )
            continue

        if registry is None:
            registry = get_steps()
        source = file_input.source
        producer = source.producer
        dep = registry.get(producer)
        if dep is None:
            raise ValueError(
                f"Step '{step.name}' input '{file_input.name}' references "
                f"unknown producer '{producer}'."
            )
        try:
            declared = dep.spec.output(source.name)
        except KeyError as error:
            raise ValueError(
                f"Step '{step.name}' input '{file_input.name}' references "
                f"unknown output '{source.name}' on step '{producer}'."
            ) from error
        if declared is not source:
            raise ValueError(
                f"Step '{step.name}' input '{file_input.name}' references "
                f"an output declaration that does not belong to '{producer}'."
            )

        if producer in steps_in_plan:
            resolved[file_input.name] = ResolvedInput(
                cwl_value=None,
                source="dep_wired",
                dep_name=producer,
                source_output=source,
            )
        else:
            path = pre_resolved.get(source)
            if path is None:
                path = dep.validated_output_paths(config)[source.name]
            resolved[file_input.name] = ResolvedInput(
                cwl_value={"class": "File", "path": str(path.resolve())},
                source="dep_disk",
                path=path,
                dep_name=producer,
                source_output=source,
            )

    return resolved


def to_cwl_inputs(resolved: dict[str, ResolvedInput]) -> dict[str, Any]:
    """Strip annotations and exclude internally wired inputs."""
    return {k: ri.cwl_value for k, ri in resolved.items() if ri.cwl_value is not None}


def resolve_step_sequence_inputs(
    step_objs: list[Step],
    config: dict,
    pre_resolved: dict[FileOutput, Path],
) -> dict[str, Any]:
    """
    Collect top-level inputs for a generated multi-step CWL job.

    Internally wired inputs are excluded.
    """
    steps_in_plan = {s.name for s in step_objs}
    step_registry = {**get_steps(), **{step.name: step for step in step_objs}}
    merged: dict[str, Any] = {}
    for step in step_objs:
        resolved = resolve_step_inputs(
            step,
            config,
            pre_resolved=pre_resolved,
            steps_in_plan=steps_in_plan,
            step_registry=step_registry,
        )
        for key, ri in resolved.items():
            if ri.cwl_value is None:
                continue
            if key in merged and merged[key] != ri.cwl_value:
                raise ValueError(
                    f"Workflow input '{key}' resolves to conflicting values. "
                    "Use distinct parameter names for unrelated step inputs."
                )
            merged.setdefault(key, ri.cwl_value)
    return merged
