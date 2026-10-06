#!/usr/bin/env python
"""
Filename: src/ASOkai/_pipeline/steps/base.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Shared lifecycle for atomic pipeline steps.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import replace
import logging
from pathlib import Path
import shlex
import subprocess
from typing import Any, ClassVar, Mapping, Sequence

from ASOkai._cwl.model import CwlCommandLineToolSpec
from ASOkai._pipeline.base import Runnable, is_valid_runnable_name
from ASOkai._pipeline.contracts.files import FileOutput
from ASOkai._pipeline.contracts.parameters import ScalarParam
from ASOkai._pipeline.contracts.step_spec import StepSpec


logger = logging.getLogger(__name__)


_N_WORKERS_PARAM = ScalarParam(
    "n_workers",
    int,
    default=1,
    doc="Number of workers allocated to this step.",
)
_MEMORY_MB_PARAM = ScalarParam(
    "memory_mb",
    int,
    default=4096,
    doc="Memory allocated to this step in mebibytes.",
)


class Step(Runnable):
    """Atomic pipeline unit backed by a generated CWL command-line tool.

    Core steps may set ``supports_multiple_workers`` only when their runtime
    consumes the automatically supplied ``args.n_workers`` value. Analysis
    steps support it through their shared base class. Steps that use the memory
    allocation may set ``consumes_memory_mb`` and read ``args.memory_mb``.
    """

    name: ClassVar[str]
    description: ClassVar[str]
    spec: ClassVar[StepSpec]
    supports_multiple_workers: ClassVar[bool] = False
    consumes_memory_mb: ClassVar[bool] = False
    listed: ClassVar[bool] = True

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Bind each declared output port to its concrete producer step."""
        super().__init_subclass__(**kwargs)
        overridden_lifecycle_methods = [
            method_name
            for method_name in ("run_cli", "validate_outputs")
            if method_name in cls.__dict__
        ]
        if overridden_lifecycle_methods:
            names = ", ".join(overridden_lifecycle_methods)
            raise TypeError(
                f"Step class '{cls.__name__}' cannot override framework-owned "
                f"lifecycle method(s): {names}. Implement run_from_args() or "
                "build_command() instead."
            )
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
        if type(cls.supports_multiple_workers) is not bool:
            raise TypeError(
                f"Step '{cls.name}' supports_multiple_workers must be a boolean."
            )
        if type(cls.consumes_memory_mb) is not bool:
            raise TypeError(
                f"Step '{cls.name}' consumes_memory_mb must be a boolean."
            )
        output_attributes = {
            attribute_name: value
            for attribute_name, value in cls.__dict__.items()
            if isinstance(value, FileOutput)
        }
        bindings: list[FileOutput] = []
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
            bindings.append(output)

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

        for output in bindings:
            output._validate_binding(cls)
        for output in bindings:
            output._bind_to(cls)

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
                param.name == _N_WORKERS_PARAM.name
                or param.cli_prefix == _N_WORKERS_PARAM.cli_prefix
            ):
                raise ValueError(
                    f"Step '{self.name}' declares reserved standard parameter "
                    f"'{_N_WORKERS_PARAM.name}'."
                )
            if self.consumes_memory_mb and (
                param.name == _MEMORY_MB_PARAM.name
                or param.cli_prefix == _MEMORY_MB_PARAM.cli_prefix
            ):
                raise ValueError(
                    f"Step '{self.name}' declares reserved standard parameter "
                    f"'{_MEMORY_MB_PARAM.name}'."
                )

    def _cwl_spec(
        self,
        config: Mapping[str, Any],
        input_configurations: Mapping[str, Mapping[str, Any]],
        parameters: Mapping[str, Any],
    ) -> CwlCommandLineToolSpec:
        """Return the CWL spec for resolved configuration and file inputs."""
        self._validate_standard_parameters()
        spec = self.spec.to_cwl_tool_spec(
            config,
            input_configurations,
            parameters=parameters,
        )
        resource_inputs = []
        if self.supports_multiple_workers:
            resource_inputs.append(_N_WORKERS_PARAM.to_cwl_input())
        if self.consumes_memory_mb:
            resource_inputs.append(_MEMORY_MB_PARAM.to_cwl_input())
        if not resource_inputs:
            return spec
        return replace(spec, inputs=[*spec.inputs, *resource_inputs])

    def build_parser(self, *, description: str | None = None):
        """Build an argparse parser from this step's parameter spec."""
        self._validate_standard_parameters()
        parser = self.spec.build_parser(description=description or self.description)
        if self.supports_multiple_workers:
            _N_WORKERS_PARAM.add_to_parser(parser)
        if self.consumes_memory_mb:
            _MEMORY_MB_PARAM.add_to_parser(parser)
        return parser

    def prepare_output_directories(self, args: argparse.Namespace) -> None:
        """Create the parent directory for every declared output argument."""
        for output in self.spec.outputs:
            path = getattr(args, output.argument_name)
            path.parent.mkdir(parents=True, exist_ok=True)

    def validate_outputs(self, args: argparse.Namespace) -> None:
        """Validate every declared output before reporting step success."""
        for output in self.spec.outputs:
            path = getattr(args, output.argument_name)
            expected = output.file_type.cwl_type
            if not (path.is_dir() if expected == "Directory" else path.is_file()):
                raise FileNotFoundError(
                    f"Step '{self.name}' did not write output "
                    f"'{output.name}' to {path}."
                )
            try:
                output.validate(path)
            except (OSError, UnicodeError, TypeError, ValueError) as error:
                raise ValueError(
                    f"Step '{self.name}' wrote invalid output "
                    f"'{output.name}' to {path}: {error}"
                ) from error

    def validate_parameters(self, values: Mapping[str, object]) -> None:
        """Validate relationships between resolved scalar parameters."""

    def validate_resources(self, values: Mapping[str, object]) -> None:
        """Validate resource settings consumed by this step."""

    def run_from_args(self, args: argparse.Namespace) -> int:
        """Execute the step using parsed arguments."""
        raise NotImplementedError(
            f"Step '{self.name}' does not implement run_from_args()."
        )

    def run_cli(self, argv: list[str] | None = None) -> int:
        """Run the shared command-line lifecycle for one step."""
        logger.info("Starting Step")
        parser = self.build_parser()
        args = parser.parse_args(argv)
        if self.supports_multiple_workers and args.n_workers < 1:
            parser.error("--n-workers must be a positive integer")
        if self.consumes_memory_mb:
            try:
                self.validate_resources({"memory_mb": args.memory_mb})
            except ValueError as error:
                parser.error(str(error))
        parameter_values = {
            parameter.name: getattr(args, parameter.name)
            for parameter in self.spec.params
        }
        try:
            self.validate_parameters(parameter_values)
        except (NotImplementedError, ValueError) as error:
            parser.error(str(error))
        self.prepare_output_directories(args)
        exit_code = self.run_from_args(args)
        if exit_code == 0:
            self.validate_outputs(args)
            logger.info("Step Completed successfully")
        return exit_code

    def resolved_parameter_values(
        self,
        config: Mapping[str, Any],
        parameters: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Resolve and validate every parameter for one invocation."""
        from ASOkai._pipeline import config as cfg

        values, errors = cfg._resolve_step_parameters(config, self, parameters)
        if errors:
            details = "\n".join(f"- {error}" for error in errors)
            raise ValueError(f"Invalid parameters for step '{self.name}':\n{details}")
        return values

    def _configuration_for_parameters(
        self,
        config: Mapping[str, Any],
        parameters: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Copy configuration with resolved values at declared global paths."""
        from ASOkai._pipeline import config as cfg

        resolved = deepcopy(dict(config))
        overrides: dict[str, Any] = {}
        names_by_path: dict[str, str] = {}
        for parameter in self.spec.params:
            if parameter.config is None:
                continue
            value = parameters[parameter.name]
            if parameter.config in overrides and (
                type(value) is not type(overrides[parameter.config])
                or value != overrides[parameter.config]
            ):
                raise ValueError(
                    f"Step '{self.name}' parameters "
                    f"'{names_by_path[parameter.config]}' and '{parameter.name}' "
                    f"have conflicting values for config path '{parameter.config}'."
                )
            overrides[parameter.config] = value
            names_by_path[parameter.config] = parameter.name
        return cfg.apply_overrides(resolved, overrides)


class ExternalCommandStep(Step):
    """A step that runs an external command through the shared lifecycle."""

    def build_command(self, args: argparse.Namespace) -> Sequence[str]:
        """Return the external command for parsed step arguments."""
        raise NotImplementedError(
            f"External step '{self.name}' does not implement build_command()."
        )

    def run_from_args(self, args: argparse.Namespace) -> int:
        """Run the external command and return its process exit code."""
        command = self.build_command(args)
        if isinstance(command, (str, bytes)) or not isinstance(command, Sequence):
            raise TypeError(
                f"External step '{self.name}' build_command() must return "
                "a sequence of strings."
            )
        argv = list(command)
        if not argv:
            raise ValueError(
                f"External step '{self.name}' command must not be empty."
            )
        if any(type(part) is not str or not part for part in argv):
            raise TypeError(
                f"External step '{self.name}' command must contain only "
                "non-empty strings."
            )
        logger.debug(
            "Running external command: %s",
            " ".join(shlex.quote(part) for part in argv),
        )
        return subprocess.run(argv, check=False).returncode
