#!/usr/bin/env python
"""
Filename: src/ASOkai/_pipeline/steps/analysis/base.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Base class and shared execution flow for analysis pipeline steps.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, ClassVar

from ASOkai.Analysis import Analysis
from ASOkai.Types import Scalar
from ASOkai._pipeline.contracts.file_types import CsvFile
from ASOkai._pipeline.contracts.files import FileOutput
from ASOkai._pipeline.steps.base import Step


class AnalysisStep(Step):
    """Analysis step with one primary CSV and optional additional outputs.

    The first ``StepSpec`` output is the primary site-keyed CSV. Additional
    outputs are written from values returned by ``additional_output_values``.
    """

    analysis_cls: ClassVar[type[Analysis] | None] = None
    supports_multiple_processes = True

    def analysis_kwargs(self, args) -> dict[str, Any]:
        """Build analysis arguments from the inputs already parsed by the step."""
        raise NotImplementedError(
            f"Analysis step '{self.name}' must implement analysis_kwargs()."
        )

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

    def _output_rows(
        self,
        results: Mapping[str, Mapping[str, Scalar]],
    ) -> list[dict[str, Scalar]]:
        """Combine site identifiers and analysis values into CSV rows."""
        output = self._primary_output
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

    def _write_primary_output(
        self,
        args,
        results: Mapping[str, Mapping[str, Scalar]],
    ) -> None:
        """Write site-keyed results through the primary CSV contract."""
        output = self._primary_output
        output.write(
            getattr(args, output.argument_name),
            self._output_rows(results),
        )

    def additional_output_values(
        self,
        analysis: Any,
        results: Mapping[str, Mapping[str, Scalar]],
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
            output.write(
                getattr(args, output.argument_name),
                values[output],
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
        analysis_kwargs = dict(provided_analysis_kwargs)
        analysis_kwargs["n_processes"] = args.n_processes
        analysis = self.analysis_cls(**analysis_kwargs)
        results = analysis.run()
        provided_additional_values: object = self.additional_output_values(
            analysis,
            results,
        )
        additional_values = self._validate_additional_output_values(
            provided_additional_values,
        )
        self._write_primary_output(args, results)
        self._write_additional_outputs(args, additional_values)
        return 0
