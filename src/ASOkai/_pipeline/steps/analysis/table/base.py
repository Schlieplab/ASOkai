#!/usr/bin/env python
"""
Filename: src/ASOkai/_pipeline/steps/analysis/table/base.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: CSV table output contract for analysis pipeline steps.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ASOkai.Analysis import Analysis
from ASOkai.Types import Scalar
from ASOkai._pipeline.contracts.file_types import CsvFile
from ASOkai._pipeline.contracts.files import FileOutput
from ASOkai._pipeline.steps.analysis.base import AnalysisStep


class TableAnalysisStep(AnalysisStep):
    """Write analysis results to a primary CSV and optional later outputs.

    The first StepSpec output is the result table. Additional outputs receive
    values from additional_output_values.
    """

    @property
    def _primary_output(self) -> FileOutput:
        """Return the first output, which owns the primary analysis table."""
        if not self.spec.outputs:
            raise RuntimeError(
                f"Analysis step '{self.name}' does not declare an output."
            )
        return self.spec.outputs[0]

    @property
    def _additional_outputs(self) -> tuple[FileOutput, ...]:
        """Return outputs declared after the primary analysis table."""
        return tuple(self.spec.outputs[1:])

    def _write_primary_output(
        self,
        args,
        results: list[dict[str, Scalar]],
    ) -> None:
        """Write complete rows through the primary CSV contract."""
        output = self._primary_output
        if not isinstance(output.file_type, CsvFile):
            raise TypeError(
                f"Analysis step '{self.name}' output '{output.name}' "
                "must use CsvFile."
            )
        output.write(getattr(args, output.argument_name), results)

    def additional_output_values(
        self,
        analysis: Analysis,
        results: list[dict[str, Scalar]],
    ) -> Mapping[FileOutput, Any]:
        """Return values for outputs declared after the primary CSV."""
        if self._additional_outputs:
            raise NotImplementedError(
                f"Analysis step '{self.name}' must implement "
                "additional_output_values() for its additional outputs."
            )
        return {}

    def _validate_additional_output_values(
        self,
        values: object,
    ) -> Mapping[FileOutput, Any]:
        """Return values after validating every additional declared output."""
        if not isinstance(values, Mapping):
            raise TypeError(
                f"Analysis step '{self.name}' additional_output_values() "
                "must return a mapping."
            )

        expected = set(self._additional_outputs)
        actual = set(values)
        if actual == expected:
            return values

        missing = (
            ", ".join(
                output.name
                for output in self._additional_outputs
                if output not in actual
            )
            or "none"
        )
        unexpected = (
            ", ".join(
                getattr(output, "name", repr(output))
                for output in actual - expected
            )
            or "none"
        )
        raise ValueError(
            f"Analysis step '{self.name}' additional output values do not "
            f"match its StepSpec outputs (missing: {missing}; "
            f"unexpected: {unexpected})."
        )

    def _write_additional_outputs(
        self,
        args,
        values: Mapping[FileOutput, Any],
    ) -> None:
        """Write validated values through their declared file contracts."""
        for output in self._additional_outputs:
            output.write(getattr(args, output.argument_name), values[output])

    def write_results(
        self, args, analysis: Analysis, results: list[Any]
    ) -> None:
        """Write the primary CSV and every declared additional output."""
        provided_additional_values: object = self.additional_output_values(
            analysis, results
        )
        additional_values = self._validate_additional_output_values(
            provided_additional_values
        )
        self._write_primary_output(args, results)
        self._write_additional_outputs(args, additional_values)
