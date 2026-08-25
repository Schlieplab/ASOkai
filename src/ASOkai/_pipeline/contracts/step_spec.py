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
import keyword
from pathlib import PurePosixPath
import re
from typing import Any, Mapping, Sequence

from ASOkai._types import Scalar
from ASOkai._cwl.model import CwlCommandLineToolSpec, CwlToolArgument
from ASOkai._pipeline.contracts.files import FileInput, FileOutput
from ASOkai._pipeline.contracts.parameters import ScalarParam

_PORT_NAME_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_]*")


@dataclass(frozen=True)
class StepSpec:
    """Source-of-truth metadata for a pipeline step."""

    params: Sequence[ScalarParam] = field(default_factory=tuple)
    inputs: Sequence[FileInput] = field(default_factory=tuple)
    outputs: Sequence[FileOutput] = field(default_factory=tuple)
    compatible_with: Mapping[str, Sequence[Scalar]] = field(default_factory=dict)
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
        object.__setattr__(
            self,
            "compatible_with",
            self._normalized_compatibility(),
        )

        self._require_valid_names(
            "parameter",
            [param.name for param in self.params],
        )
        self._require_valid_names(
            "input",
            [item.name for item in self.inputs],
        )
        self._require_valid_names(
            "output",
            [output.name for output in self.outputs],
        )
        self._require_unique("parameter", [param.name for param in self.params])
        self._require_unique("input", [item.name for item in self.inputs])
        self._require_unique("output", [output.name for output in self.outputs])

        authored_inputs = [param.name for param in self.params]
        authored_inputs.extend(item.name for item in self.inputs)
        self._require_unique("parameter/input", authored_inputs)

        cwl_inputs = [param.name for param in self.params if param.cwl]
        cwl_inputs.extend(item.name for item in self.inputs)
        self._require_unique("generated CWL input", cwl_inputs)

        cli_options = [param.cli_prefix for param in self.params]
        cli_options.extend(item.cli_prefix for item in self.inputs)
        cli_options.extend(output.cli_prefix for output in self.outputs)
        self._require_unique("CLI option", cli_options)
        if "--help" in cli_options:
            raise ValueError("StepSpec CLI option '--help' is reserved.")

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

    def _normalized_compatibility(self) -> dict[str, tuple[Scalar, ...]]:
        """Validate and normalize declared step compatibility."""
        if not isinstance(self.compatible_with, Mapping):
            raise TypeError("StepSpec.compatible_with must be a mapping.")

        compatible_with: dict[str, tuple[Scalar, ...]] = {}
        for path, values in self.compatible_with.items():
            if (
                type(path) is not str
                or not path.strip()
                or any(not part.strip() for part in path.split("."))
            ):
                raise ValueError(
                    "StepSpec.compatible_with keys must be dotted config paths."
                )
            if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
                raise TypeError(
                    f"StepSpec.compatible_with[{path!r}] must be a sequence "
                    "of values."
                )
            if not values:
                raise ValueError(
                    f"StepSpec.compatible_with[{path!r}] must not be empty."
                )
            if any(
                value is not None
                and type(value) not in (str, int, float, bool)
                for value in values
            ):
                raise TypeError(
                    f"StepSpec.compatible_with[{path!r}] must contain only "
                    "scalar configuration values."
                )
            compatible_with[path] = tuple(values)
        return compatible_with

    @staticmethod
    def _require_valid_names(label: str, names: list[str]) -> None:
        invalid = sorted({
            repr(name)
            for name in names
            if (
                type(name) is not str
                or _PORT_NAME_PATTERN.fullmatch(name) is None
                or keyword.iskeyword(name)
            )
        })
        if invalid:
            joined = ", ".join(invalid)
            raise ValueError(
                f"Invalid {label} name(s): {joined}. Names must start with a "
                "letter, contain only letters, numbers, and underscores, and "
                "not be a Python keyword."
            )

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

    def input(self, name: str) -> FileInput:
        """Return one declared file input by name."""
        for item in self.inputs:
            if item.name == name:
                return item
        raise KeyError(f"Unknown step input: {name!r}.")

    def parameter(self, name: str) -> ScalarParam:
        """Return one declared scalar parameter by name."""
        for parameter in self.params:
            if parameter.name == name:
                return parameter
        raise KeyError(f"Unknown step parameter: {name!r}.")

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
