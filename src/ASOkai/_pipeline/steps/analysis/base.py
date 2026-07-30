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

from collections.abc import Mapping
from typing import Any, ClassVar

from ASOkai._types import Scalar
from ASOkai._pipeline.contracts.file_types import CsvFile
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
                f"Analysis step '{self.name}' must override output_arg "
                "for multiple outputs."
            )
        return getattr(args, outputs[0].argument_name)

    def _output_rows(
        self,
        results: Mapping[str, Mapping[str, Scalar]],
    ) -> list[dict[str, Scalar]]:
        """Combine site identifiers and analysis values into CSV rows."""
        output = self.spec.outputs[0]
        if not isinstance(output.file_type, CsvFile):
            raise TypeError(
                f"Analysis step '{self.name}' output '{output.name}' "
                "must use CsvFile."
            )

        index_names = tuple(output.file_type.index)
        if len(index_names) != 1:
            raise ValueError(
                f"Analysis step '{self.name}' output '{output.name}' "
                "must declare exactly one index column."
            )
        index_name = index_names[0]

        rows = []
        for index_value, values in results.items():
            if index_name in values:
                raise ValueError(
                    f"Analysis result '{index_value}' contains the index "
                    f"column '{index_name}'."
                )
            rows.append({
                index_name: index_value,
                **values,
            })
        return rows

    def write_analysis_output(
        self,
        args,
        results: Mapping[str, Mapping[str, Scalar]],
    ) -> None:
        """Write site-keyed analysis results through the declared CSV contract."""
        output_path = self.output_arg(args)
        self.spec.outputs[0].write(
            output_path,
            self._output_rows(results),
        )

    def run_from_args(self, args) -> int:
        """Load inputs, run the configured analysis, and write its CSV output."""
        if self.analysis_cls is None:
            raise RuntimeError(
                f"Analysis step '{self.name}' does not define analysis_cls."
            )

        analysis_kwargs = self.analysis_kwargs(args)
        analysis_kwargs.setdefault("n_processes", args.n_processes)
        analysis = self.analysis_cls(**analysis_kwargs)
        self.write_analysis_output(args, analysis.run())
        return 0
