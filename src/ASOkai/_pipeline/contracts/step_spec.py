#!/usr/bin/env python
"""
Filename: src/ASOkai/_pipeline/contracts/step_spec.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Version: 0.1.1
Description: Source-of-truth declarations for pipeline steps.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence

from ASOkai._cwl.model import CwlCommandLineToolSpec, CwlToolArgument
from ASOkai._pipeline.contracts.files import FileInput, FileOutput
from ASOkai._pipeline.contracts.parameters import ScalarParam


@dataclass(frozen=True)
class StepSpec:
    """Source-of-truth metadata for a pipeline step."""

    params: Sequence[ScalarParam] = field(default_factory=tuple)
    inputs: Sequence[FileInput] = field(default_factory=tuple)
    outputs: Sequence[FileOutput] = field(default_factory=tuple)
    base_command: list[str] | None = None
    requirements: dict[str, Any] = field(default_factory=dict)
    arguments: Sequence[CwlToolArgument] = field(default_factory=tuple)
    extra: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Reject declarations that would produce ambiguous CLI or CWL ports."""
        object.__setattr__(self, "params", tuple(self.params))
        object.__setattr__(self, "inputs", tuple(self.inputs))
        object.__setattr__(self, "outputs", tuple(self.outputs))
        object.__setattr__(self, "arguments", tuple(self.arguments))

        self._require_unique("parameter", [param.name for param in self.params])
        self._require_unique("input", [item.name for item in self.inputs])
        self._require_unique("output", [output.name for output in self.outputs])

        authored_inputs = [param.name for param in self.params]
        authored_inputs.extend(item.name for item in self.inputs)
        self._require_unique("parameter/input", authored_inputs)

        cwl_inputs = [param.name for param in self.params if param.cwl]
        cwl_inputs.extend(item.name for item in self.inputs)
        self._require_unique("generated CWL input", cwl_inputs)

        declared_cwl_inputs = {
            param.name for param in self.params if param.cwl
        }
        declared_cwl_inputs.update(item.name for item in self.inputs)
        for output in self.outputs:
            missing_inputs = output.destination.input_names() - declared_cwl_inputs
            if missing_inputs:
                names = ", ".join(sorted(missing_inputs))
                raise ValueError(
                    f"Output '{output.name}' path references undeclared CWL "
                    f"input(s): {names}."
                )

        reserved = {
            "cwlVersion",
            "class",
            "baseCommand",
            "doc",
            "requirements",
            "arguments",
            "inputs",
            "outputs",
        }
        conflicting_extra = reserved.intersection(self.extra)
        if conflicting_extra:
            names = ", ".join(sorted(conflicting_extra))
            raise ValueError(f"StepSpec.extra cannot replace reserved keys: {names}.")

    @staticmethod
    def _require_unique(label: str, names: list[str]) -> None:
        duplicates = sorted({name for name in names if names.count(name) > 1})
        if duplicates:
            joined = ", ".join(duplicates)
            raise ValueError(f"Duplicate {label} name(s): {joined}.")

    def to_cwl_tool_spec(
        self,
        values: Mapping[str, Any] | None = None,
    ) -> CwlCommandLineToolSpec:
        """Return the low-level CommandLineTool spec generated from this step spec."""
        values = values or {}
        working_filenames = [
            output.working_filename(values)
            for output in self.outputs
        ]
        self._require_unique("CWL output filename", working_filenames)
        inputs = [
            item
            for param in self.params
            if (item := param.to_cwl_input()) is not None
        ]
        inputs.extend(
            input_param.to_cwl_input()
            for input_param in self.inputs
        )
        return CwlCommandLineToolSpec(
            base_command=self.base_command,
            requirements=deepcopy(self.requirements),
            arguments=[
                *self.arguments,
                *(output.to_cwl_argument(values) for output in self.outputs),
            ],
            inputs=inputs,
            outputs=[output.to_cwl_output(values) for output in self.outputs],
            extra=deepcopy(self.extra),
        )

    def config_map(self) -> dict[str, str]:
        """Return CWL input names mapped to config dot paths."""
        return {
            param.name: param.config
            for param in self.params
            if param.cwl and param.config
        }

    def input_overrides(self) -> dict[str, str]:
        """Return CWL input names mapped to optional file override config paths."""
        return {
            item.name: item.override
            for item in self.inputs
            if item.override
        }

    def input(self, name: str) -> FileInput:
        """Return one declared file input by name."""
        for item in self.inputs:
            if item.name == name:
                return item
        raise KeyError(f"Unknown step input: {name!r}.")

    def output(self, name: str) -> FileOutput:
        """Return one declared output by name."""
        for output in self.outputs:
            if output.name == name:
                return output
        raise KeyError(f"Unknown step output: {name!r}.")

    def dependencies(self) -> tuple[str, ...]:
        """Return producer step names, derived from source outputs."""
        return tuple(dict.fromkeys(item.source.producer for item in self.inputs))

    def output_names(self) -> tuple[str, ...]:
        """Return produced output names in declaration order."""
        return tuple(output.name for output in self.outputs)

    def output_relative_path(
        self,
        name: str,
        values: Mapping[str, Any],
    ) -> PurePosixPath:
        """Render one declared path relative to the configured data directory."""
        for output in self.outputs:
            if output.name == name:
                return output.destination.render(values)
        raise KeyError(f"Unknown step output: {name!r}.")

    def validate_output_paths(self, output_paths: dict[str, Path]) -> None:
        """Ensure runtime output paths exactly implement the declared outputs."""
        declared = set(self.output_names())
        actual = set(output_paths)
        if declared == actual:
            return

        missing = ", ".join(sorted(declared - actual)) or "none"
        unexpected = ", ".join(sorted(actual - declared)) or "none"
        raise ValueError(
            "Step output_paths() does not match StepSpec outputs "
            f"(missing: {missing}; unexpected: {unexpected})."
        )

    def build_parser(
        self,
        *,
        description: str | None = None,
    ) -> argparse.ArgumentParser:
        """Build an argparse parser from declared step parameters."""
        parser = argparse.ArgumentParser(description=description)
        for param in self.params:
            param.add_to_parser(parser)
        for input_param in self.inputs:
            input_param.add_to_parser(parser)
        for output in self.outputs:
            output.add_to_parser(parser)
        return parser
