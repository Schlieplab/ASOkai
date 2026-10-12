#!/usr/bin/env python
"""
Filename: src/ASOkai/_pipeline/contracts/step_spec.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Source-of-truth declarations for pipeline steps.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import dataclass, field
import keyword
import re
from typing import Any, Mapping, Sequence

from ASOkai.Types import Scalar
from ASOkai._cwl.model import CwlCommandLineToolSpec, _UNSET
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
    requirements: Mapping[str, Any] = field(default_factory=dict)
    extra: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Reject declarations that would produce ambiguous CLI or CWL ports."""
        object.__setattr__(self, "params", tuple(self.params))
        object.__setattr__(self, "inputs", tuple(self.inputs))
        object.__setattr__(self, "outputs", tuple(self.outputs))
        if any(not isinstance(param, ScalarParam) for param in self.params):
            raise TypeError(
                "StepSpec.params must contain only ScalarParam values."
            )
        if any(not isinstance(item, FileInput) for item in self.inputs):
            raise TypeError(
                "StepSpec.inputs must contain only FileInput values."
            )
        if any(not isinstance(output, FileOutput) for output in self.outputs):
            raise TypeError(
                "StepSpec.outputs must contain only FileOutput values."
            )
        if not isinstance(self.requirements, Mapping):
            raise TypeError("StepSpec.requirements must be a mapping.")
        if not isinstance(self.extra, Mapping):
            raise TypeError("StepSpec.extra must be a mapping.")
        object.__setattr__(
            self,
            "requirements",
            deepcopy(dict(self.requirements)),
        )
        object.__setattr__(self, "extra", deepcopy(dict(self.extra)))
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

        declared_file_inputs = {item.name for item in self.inputs}
        for output in self.outputs:
            unknown_inputs = (
                output.destination.input_names() - declared_file_inputs
            )
            if unknown_inputs:
                names = ", ".join(sorted(unknown_inputs))
                raise ValueError(
                    f"Output '{output.name}' references undeclared file "
                    f"input(s): {names}."
                )

        cli_options = [param.cli_prefix for param in self.params]
        cli_options.extend(item.cli_prefix for item in self.inputs)
        cli_options.extend(output.cli_prefix for output in self.outputs)
        self._require_unique("CLI option", cli_options)
        if "--help" in cli_options:
            raise ValueError("StepSpec CLI option '--help' is reserved.")

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
        config: Mapping[str, Any] | None = None,
        input_configurations: Mapping[
            str,
            Mapping[str, Any],
        ] | None = None,
        *,
        parameters: Mapping[str, Any] | None = None,
    ) -> CwlCommandLineToolSpec:
        """Return the low-level CommandLineTool spec generated from this step spec."""
        config = config or {}
        working_filenames = [
            output.working_filename(config, input_configurations)
            for output in self.outputs
        ]
        self._require_unique("CWL output filename", working_filenames)
        inputs = []
        arguments = [
            output.to_cwl_argument(config, input_configurations)
            for output in self.outputs
        ]
        for param in self.params:
            value = parameters[param.name] if parameters is not None else _UNSET
            inputs.append(param.to_cwl_input(value=value))
            argument = param.to_cwl_argument(value=value)
            if argument is not None:
                arguments.append(argument)
        inputs.extend(
            input_param.to_cwl_input()
            for input_param in self.inputs
        )
        return CwlCommandLineToolSpec(
            requirements=deepcopy(dict(self.requirements)),
            arguments=arguments,
            inputs=inputs,
            outputs=[
                output.to_cwl_output(config, input_configurations)
                for output in self.outputs
            ],
            extra=deepcopy(dict(self.extra)),
        )

    def config_map(self) -> dict[str, str]:
        """Return CWL input names mapped to config dot paths."""
        return {
            param.name: param.config
            for param in self.params
            if param.config
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
        return tuple(
            dict.fromkeys(
                item.source.producer
                for item in self.inputs
                if item.source is not None
            )
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
