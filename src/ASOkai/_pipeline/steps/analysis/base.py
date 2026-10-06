#!/usr/bin/env python
"""
Filename: src/ASOkai/_pipeline/steps/analysis/base.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Base class and shared execution flow for analysis pipeline steps.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, ClassVar

from ASOkai.Analysis import Analysis, BatchAnalysis, PerUnitAnalysis
from ASOkai._pipeline.steps.base import Step


class AnalysisStep(Step):
    """Run an analysis and delegate result serialization to a subclass."""

    analysis_cls: ClassVar[type[Analysis] | None] = None
    supports_multiple_workers = True

    def analysis_kwargs(self, args) -> dict[str, Any]:
        """Build concrete-analysis constructor arguments from parsed inputs."""
        return {}

    def analysis_units(self, args) -> Iterable[Any]:
        """Return analysis units from inputs already parsed by the step."""
        raise NotImplementedError(
            f"Analysis step '{self.name}' must implement analysis_units()."
        )

    def write_results(
        self, args, analysis: Analysis, results: list[Any]
    ) -> None:
        """Write the analysis results through declared output contracts."""
        raise NotImplementedError(
            f"Analysis step '{self.name}' must implement write_results()."
        )

    def run_from_args(self, args) -> int:
        """Run the configured analysis and write all declared outputs."""
        if self.analysis_cls is None:
            raise RuntimeError(
                f"Analysis step '{self.name}' does not define analysis_cls."
            )

        provided_analysis_kwargs: object = self.analysis_kwargs(args)
        if not isinstance(provided_analysis_kwargs, Mapping):
            raise TypeError(
                f"Analysis step '{self.name}' analysis_kwargs() must return "
                "a mapping."
            )
        analysis = self.analysis_cls(**dict(provided_analysis_kwargs))
        units = self.analysis_units(args)
        if not isinstance(analysis, (PerUnitAnalysis, BatchAnalysis)):
            raise TypeError("analysis_cls must use PerUnitAnalysis or BatchAnalysis.")
        results = analysis.run(units, n_workers=args.n_workers)
        self.write_results(args, analysis, results)
        return 0
