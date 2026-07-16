#!/usr/bin/env python
"""
Filename: src/ASOkai/_pipeline/base.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Version: 0.1.1
Description: Base protocols for steps and CLI-level step collections.
License: LGPL-3.0-or-later
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, ClassVar, Protocol, runtime_checkable

from ASOkai._cwl.spec import CwlCommandLineToolSpec, StepSpec


@runtime_checkable
class Runnable(Protocol):
    """
    Shared contract for every named pipeline unit or CLI collection.
    """

    name: ClassVar[str]
    description: ClassVar[str]

    def output_paths(self, config: dict) -> dict[str, Path]:
        ...

    def outputs_exist(self, config: dict) -> bool:
        ...

    def cleanup(self, config: dict) -> None:
        ...


class Step(Runnable):
    """Atomic pipeline unit backed by a generated CWL command-line tool."""

    name: ClassVar[str]
    description: ClassVar[str]
    dependencies: ClassVar[list[str]]
    cli_module: ClassVar[str]
    spec: ClassVar[StepSpec]

    @property
    def config_map(self) -> dict[str, str]:
        """Return config-backed CWL inputs for this step."""
        return self.spec.config_map()

    @property
    def input_overrides(self) -> dict[str, str]:
        """Return optional file override inputs for this step."""
        return self.spec.input_overrides()

    @property
    def cwl_spec(self) -> CwlCommandLineToolSpec:
        """Return the generated lower-level CWL tool spec for this step."""
        return self.spec.to_cwl_tool_spec()

    def build_parser(self, *, description: str | None = None):
        """Build an argparse parser from this step's parameter spec."""
        return self.spec.build_parser(description=description or self.description)

    def _output_template_values(self, config: dict) -> dict[str, Any]:
        """Resolve config-backed values used by output path templates."""
        from ASOkai._pipeline import config as cfg

        values: dict[str, Any] = {}
        for param in (*self.spec.params, *self.spec.inputs):
            if not param.config:
                continue
            try:
                values[param.name] = cfg.resolve(config, param.config)
            except KeyError:
                pass
        return values

    def output_relative_path(self, name: str, config: dict) -> Path:
        """Render a declared output path relative to ``config['datadir']``."""
        path = self.spec.output_relative_path(
            name,
            self._output_template_values(config),
        )
        return Path(*path.parts)

    def validated_output_paths(self, config: dict) -> dict[str, Path]:
        """Return output paths after checking them against the step specification."""
        paths = self.output_paths(config)
        self.spec.validate_output_paths(paths)
        datadir = Path(config["datadir"])
        for name, path in paths.items():
            expected = datadir / self.output_relative_path(name, config)
            if path != expected:
                raise ValueError(
                    f"Output '{name}' path does not match its destination template "
                    f"(expected: {expected}; actual: {path})."
                )
        return paths

    def output_paths(self, config: dict) -> dict[str, Path]:
        """Return all declared output paths below the configured data directory."""
        datadir = Path(config["datadir"])
        return {
            output.name: datadir / self.output_relative_path(output.name, config)
            for output in self.spec.outputs
        }

    def outputs_exist(self, config: dict) -> bool:
        """Return whether every declared output currently exists."""
        return all(path.exists() for path in self.output_paths(config).values())

    def cleanup(self, config: dict) -> None:
        """Remove all declared output files that currently exist."""
        for path in self.output_paths(config).values():
            if path.exists():
                path.unlink()


class CoreStep(Step):
    """Pipeline step that prepares, downloads, builds, or transforms core data."""


class AnalysisStep(Step):
    """Pipeline step that runs analysis logic and writes analysis results."""

    analysis_cls: ClassVar[type | None] = None

    def load_analysis_inputs(self, args) -> dict[str, Any]:
        """Load input objects needed to construct the analysis."""
        return {}

    def analysis_kwargs(self, args, inputs: dict[str, Any]) -> dict[str, Any]:
        """Build keyword arguments for the configured analysis class."""
        return {}

    def analysis_metadata(self, args, inputs: dict[str, Any]) -> dict[str, Any]:
        """Build output metadata written next to analysis results."""
        return {"analysis": self.name}

    def output_arg(self, args):
        """Return the parsed output path for single-output analysis steps."""
        outputs = self.spec.outputs
        if len(outputs) != 1:
            raise RuntimeError(
                f"Analysis step '{self.name}' must override output_arg for multiple outputs."
            )
        return getattr(args, outputs[0].argument_name)

    def write_analysis_output(self, args, payload: dict[str, Any]) -> None:
        """Write the analysis payload."""
        output = self.output_arg(args)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, indent=4))

    def run_from_args(self, args) -> int:
        """Load inputs, run the configured analysis, and write its JSON output."""
        if self.analysis_cls is None:
            raise RuntimeError(f"Analysis step '{self.name}' does not define analysis_cls.")

        inputs = self.load_analysis_inputs(args)
        analysis = self.analysis_cls(**self.analysis_kwargs(args, inputs))
        payload = {
            **self.analysis_metadata(args, inputs),
            "results": analysis.run(),
        }
        self.write_analysis_output(args, payload)
        return 0


@runtime_checkable
class Task(Runnable, Protocol):
    """CLI-level named collection of Steps."""

    steps: list[Step]


@runtime_checkable
class Workflow(Runnable, Protocol):
    """
    CLI-level named collection of Runnables.

    Jobs are generated by recursively flattening ``members`` to Steps.
    """

    members: list[Runnable]
