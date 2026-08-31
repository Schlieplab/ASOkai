#!/usr/bin/env python
"""
Filename: src/ASOkai/_pipeline/steps/base.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Version: 0.1.1
Description: Shared lifecycle for atomic pipeline steps.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from typing import Any, ClassVar, Mapping

from ASOkai._cwl.model import CwlCommandLineToolSpec
from ASOkai._pipeline.base import Runnable, is_valid_runnable_name
from ASOkai._pipeline.contracts.files import FileOutput
from ASOkai._pipeline.contracts.parameters import ScalarParam
from ASOkai._pipeline.contracts.step_spec import StepSpec


_N_PROCESSES_PARAM = ScalarParam(
    "n_processes",
    int,
    default=1,
    doc="Number of processes allocated to this step.",
)


class Step(Runnable):
    """Atomic pipeline unit backed by a generated CWL command-line tool.

    Core steps may set ``supports_multiple_processes`` only when their runtime
    consumes the automatically supplied ``args.n_processes`` value. Analysis
    steps support it through their shared base class.
    """

    name: ClassVar[str]
    description: ClassVar[str]
    spec: ClassVar[StepSpec]
    supports_multiple_processes: ClassVar[bool] = False

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Bind each declared output port to its concrete producer step."""
        super().__init_subclass__(**kwargs)
        overridden_path_methods = [
            method_name
            for method_name in ("output_relative_path", "output_paths")
            if method_name in cls.__dict__
        ]
        if overridden_path_methods:
            names = ", ".join(overridden_path_methods)
            raise TypeError(
                f"Step class '{cls.__name__}' cannot override framework-owned "
                f"output path method(s): {names}. Declare paths through "
                "FileOutput.destination."
            )
        spec = cls.__dict__.get("spec")
        if spec is None:
            if "name" in cls.__dict__:
                inherited_spec = getattr(cls, "spec", None)
                if isinstance(inherited_spec, StepSpec) and inherited_spec.outputs:
                    raise TypeError(
                        f"Step '{cls.name}' must redeclare its outputs and spec."
                    )
            return
        if not isinstance(spec, StepSpec):
            raise TypeError(f"Step '{cls.__name__}.spec' must be a StepSpec.")
        step_name = getattr(cls, "name", None)
        if not is_valid_runnable_name(step_name):
            raise TypeError(
                f"Step class '{cls.__name__}' requires a name that starts "
                "with a letter or number and contains only letters, numbers, "
                "hyphens, and underscores."
            )
        if type(cls.supports_multiple_processes) is not bool:
            raise TypeError(
                f"Step '{cls.name}' supports_multiple_processes must be a boolean."
            )

        output_attributes = {
            attribute_name: value
            for attribute_name, value in cls.__dict__.items()
            if isinstance(value, FileOutput)
        }
        bindings: list[tuple[FileOutput, str]] = []
        for output in spec.outputs:
            attribute_names = [
                attribute_name
                for attribute_name, value in output_attributes.items()
                if value is output
            ]
            if len(attribute_names) != 1:
                raise TypeError(
                    f"Step '{cls.name}' output '{output.name}' must be declared "
                    "once as a class attribute and reused in StepSpec.outputs."
                )
            bindings.append((output, attribute_names[0]))

        undeclared = [
            attribute_name
            for attribute_name, output in output_attributes.items()
            if all(output is not declared for declared in spec.outputs)
        ]
        if undeclared:
            names = ", ".join(sorted(undeclared))
            raise TypeError(
                f"Step '{cls.name}' has FileOutput attribute(s) missing from "
                f"StepSpec.outputs: {names}."
            )

        for output, attribute_name in bindings:
            output._validate_binding(cls, attribute_name)
        for output, attribute_name in bindings:
            output._bind_to(cls, attribute_name)

    @property
    def dependencies(self) -> list[str]:
        """Return dependencies derived from the step's file inputs."""
        return list(self.spec.dependencies())

    @property
    def config_map(self) -> dict[str, str]:
        """Return config-backed CWL inputs for this step."""
        return self.spec.config_map()

    def validate_output_declaration(self) -> None:
        """Require at least one file output for planning and publication."""
        if not self.spec.outputs:
            raise ValueError(
                f"Step '{self.name}' must declare at least one file output."
            )

    def _validate_standard_parameters(self) -> None:
        for param in (*self.spec.params, *self.spec.inputs):
            if (
                param.name == _N_PROCESSES_PARAM.name
                or param.cli_prefix == _N_PROCESSES_PARAM.cli_prefix
            ):
                raise ValueError(
                    f"Step '{self.name}' declares reserved standard parameter "
                    f"'{_N_PROCESSES_PARAM.name}'."
                )

    def _cwl_spec(
        self,
        config: Mapping[str, Any],
        input_configurations: Mapping[str, Mapping[str, Any]],
    ) -> CwlCommandLineToolSpec:
        """Return the CWL spec for resolved configuration and file inputs."""
        self._validate_standard_parameters()
        spec = self.spec.to_cwl_tool_spec(
            config,
            input_configurations,
        )
        if not self.supports_multiple_processes:
            return spec
        n_processes_input = _N_PROCESSES_PARAM.to_cwl_input()
        if n_processes_input is None:
            raise RuntimeError("The standard n_processes parameter must be a CWL input.")
        return replace(spec, inputs=[*spec.inputs, n_processes_input])

    def build_parser(self, *, description: str | None = None):
        """Build an argparse parser from this step's parameter spec."""
        self._validate_standard_parameters()
        parser = self.spec.build_parser(description=description or self.description)
        if self.supports_multiple_processes:
            _N_PROCESSES_PARAM.add_to_parser(parser)
        return parser

    def prepare_output_directories(self, args: argparse.Namespace) -> None:
        """Create the parent directory for every declared output argument."""
        for output in self.spec.outputs:
            path = getattr(args, output.argument_name)
            path.parent.mkdir(parents=True, exist_ok=True)

    def validate_parameters(self, values: Mapping[str, object]) -> None:
        """Validate relationships between resolved scalar parameters."""

    def run_from_args(self, args: argparse.Namespace) -> int:
        """Execute the step using parsed arguments."""
        raise NotImplementedError(
            f"Step '{self.name}' does not implement run_from_args()."
        )

    def run_cli(self, argv: list[str] | None = None) -> int:
        """Run the shared command-line lifecycle for one step."""
        parser = self.build_parser()
        args = parser.parse_args(argv)
        self.prepare_output_directories(args)
        return self.run_from_args(args)

    def resolved_parameter_values(
        self,
        config: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Return config-backed parameter values that can be resolved."""
        from ASOkai._pipeline import config as cfg

        values: dict[str, Any] = {}
        for parameter in self.spec.params:
            if parameter.config is None:
                continue
            try:
                values[parameter.name] = cfg.resolve_parameter_value(
                    config,
                    parameter,
                )
            except KeyError:
                pass
        return values

    def _configuration_with_defaults(
        self,
        config: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Return a configuration copy with this step's defaults applied."""
        from ASOkai._pipeline import config as cfg

        resolved = deepcopy(dict(config))
        overrides: dict[str, Any] = {}
        for parameter in self.spec.params:
            if parameter.config is None:
                continue
            try:
                overrides[parameter.config] = cfg.resolve_parameter_value(
                    config,
                    parameter,
                )
            except KeyError:
                continue
        return cfg.apply_overrides(resolved, overrides)
