#!/usr/bin/env python
"""
Filename: src/ASOkai/_pipeline/steps/analysis/base.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Version: 0.1.1
Description: Base class and shared execution flow for analysis pipeline steps.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

from typing import Any, ClassVar

from ASOkai._pipeline.steps.base import Step


class AnalysisStep(Step):
    """Pipeline step that runs analysis logic and writes analysis results."""

    analysis_cls: ClassVar[type | None] = None

    def analysis_kwargs(self, args) -> dict[str, Any]:
        """Build analysis arguments from the inputs already parsed by the step."""
        return {}

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
        output_path = self.output_arg(args)
        self.spec.outputs[0].write(output_path, payload)

    def run_from_args(self, args) -> int:
        """Load inputs, run the configured analysis, and write its JSON output."""
        if self.analysis_cls is None:
            raise RuntimeError(f"Analysis step '{self.name}' does not define analysis_cls.")

        analysis_kwargs = self.analysis_kwargs(args)
        analysis_kwargs.setdefault("n_processes", args.n_processes)
        analysis = self.analysis_cls(**analysis_kwargs)
        metadata = {
            "analysis": self.name,
            **{
                param.name: getattr(args, param.name)
                for param in self.spec.params
            },
        }
        payload = {
            **metadata,
            "results": analysis.run(),
        }
        self.write_analysis_output(args, payload)
        return 0
