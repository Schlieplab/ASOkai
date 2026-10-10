#!/usr/bin/env python
"""
Filename: tests/unit/test_analysis_step_base.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Tests for shared analysis-step execution and output contracts.
License: LGPL-3.0-or-later
"""

from argparse import Namespace
from collections.abc import Iterable
from typing import Any, ClassVar, cast

import pytest

from ASOkai.Analysis import BatchAnalysis, PerUnitAnalysis
from ASOkai.Plugins import (
    AnalysisStep,
    CsvFile,
    FileOutput,
    JsonFile,
    ScalarParam,
    StepSpec,
    TableAnalysisStep,
)
from ASOkai.Types import AnalysisUnitType, Scalar
from ASOkai._pipeline.validation import validate_component


class FakeAnalysis(PerUnitAnalysis):
    analysis_unit_type: ClassVar[AnalysisUnitType] = "site"
    last_worker_count: ClassVar[int | None] = None

    def __init__(self, value: int) -> None:
        self.value = value

    def analyze_unit(self, unit: str) -> list[dict[str, Scalar]]:
        return [{"site_id": unit, "value": self.value}]


@pytest.fixture(autouse=True)
def record_fake_analysis_workers(monkeypatch):
    original_stream = PerUnitAnalysis.stream

    def record_stream(analysis, units, *, n_workers=1):
        if isinstance(analysis, FakeAnalysis):
            type(analysis).last_worker_count = n_workers
        return original_stream(analysis, units, n_workers=n_workers)

    # run() streams too, so this records whichever one a step uses.
    monkeypatch.setattr(PerUnitAnalysis, "stream", record_stream)


class TextAnalysis(PerUnitAnalysis):
    analysis_unit_type: ClassVar[AnalysisUnitType] = "site"

    def analyze_unit(self, unit: str) -> list[str]:
        return [unit.upper()]


class JsonAnalysisStep(AnalysisStep):
    name = "json-analysis"
    description = "Write non-tabular analysis results."
    analysis_cls = TextAnalysis
    json_output = FileOutput(
        "json", destination="results.json", file_type=JsonFile()
    )
    spec = StepSpec(outputs=[json_output])

    def analysis_units(self, args):
        return ["site-1", "site-2"]

    def write_results(self, args, analysis, results):
        # JSON needs the whole document, so this step collects its rows.
        self.json_output.write(args.json_output, {"values": list(results)})


class FakeAnalysisStep(TableAnalysisStep):
    name = "fake-analysis"
    description = "Fake analysis."
    analysis_cls = FakeAnalysis
    analysis_output = FileOutput(
        "analysis",
        destination="analysis.csv",
        file_type=CsvFile(index={"site_id": str}, columns={"value": int}),
    )
    spec = StepSpec(params=[ScalarParam("value", int)], outputs=[analysis_output])

    def analysis_kwargs(self, args):
        return {"value": args.value}

    def analysis_units(self, args):
        return ["site-1"]


class MissingAnalysisClassStep(FakeAnalysisStep):
    analysis_cls = None


class MissingAnalysisUnitsStep(FakeAnalysisStep):
    def analysis_units(self, args):
        return AnalysisStep.analysis_units(self, args)


class EmptyAnalysisStep(FakeAnalysisStep):
    def analysis_units(self, args):
        return []


class InvalidAnalysisKwargsStep(FakeAnalysisStep):
    def analysis_kwargs(self, args):
        return cast(Any, None)


class MissingColumnAnalysis(FakeAnalysis):
    def analyze_unit(self, unit: str) -> list[dict[str, Scalar]]:
        return [{"site_id": unit}]


class MissingColumnStep(FakeAnalysisStep):
    analysis_cls = MissingColumnAnalysis


class MultiOutputAnalysisStep(FakeAnalysisStep):
    name = "multi-output-analysis"
    analysis_output = FileOutput(
        "analysis",
        destination="analysis.csv",
        file_type=CsvFile(index={"site_id": str}, columns={"value": int}),
    )
    doubled_output = FileOutput(
        "doubled",
        destination="doubled.csv",
        file_type=CsvFile(index={"site_id": str}, columns={"double_value": int}),
    )
    summary_output = FileOutput(
        "summary", destination="summary.json", file_type=JsonFile()
    )
    spec = StepSpec(
        params=[ScalarParam("value", int)],
        outputs=[analysis_output, doubled_output, summary_output],
    )

    def additional_output_values(self, analysis, results):
        return {
            self.doubled_output: [
                {
                    "site_id": row["site_id"],
                    "double_value": cast(int, row["value"]) * 2,
                }
                for row in results
            ],
            self.summary_output: {
                "site_count": len(results),
                "worker_count": getattr(analysis, "last_worker_count"),
            },
        }


class MissingAdditionalOutputValueStep(MultiOutputAnalysisStep):
    def additional_output_values(self, analysis, results):
        return {self.summary_output: {"site_count": len(results)}}


class InvalidAdditionalOutputValuesStep(MultiOutputAnalysisStep):
    def additional_output_values(self, analysis, results):
        return cast(Any, None)


class UnexpectedAdditionalOutputValueStep(MultiOutputAnalysisStep):
    def additional_output_values(self, analysis, results):
        values = dict(super().additional_output_values(analysis, results))
        values[
            FileOutput(
                "unexpected", destination="unexpected.json", file_type=JsonFile()
            )
        ] = {"unexpected": True}
        return values


class PairAnalysis(PerUnitAnalysis):
    analysis_unit_type: ClassVar[AnalysisUnitType] = "binding"

    def analyze_unit(self, unit: str) -> list[dict[str, Scalar]]:
        return [
            {"therapeutic_id": "t1", "site_id": unit, "value": 1},
            {"therapeutic_id": "t2", "site_id": unit, "value": 2},
        ]


class PairAnalysisStep(TableAnalysisStep):
    name = "pair-analysis"
    description = "Two complete binding rows per site."
    analysis_cls = PairAnalysis
    analysis_output = FileOutput(
        "analysis",
        destination="pairs.csv",
        file_type=CsvFile(
            index={"therapeutic_id": str, "site_id": str},
            columns={"value": int},
        ),
    )
    spec = StepSpec(outputs=[analysis_output])

    def analysis_units(self, args):
        return ["site-1"]


class DuplicatePairAnalysis(PairAnalysis):
    def analyze_unit(self, unit: str) -> list[dict[str, Scalar]]:
        return [
            {"therapeutic_id": "t1", "site_id": unit, "value": 1},
            {"therapeutic_id": "t1", "site_id": unit, "value": 2},
        ]


class DuplicatePairStep(PairAnalysisStep):
    analysis_cls = DuplicatePairAnalysis


class RecordingBatch(BatchAnalysis):
    analysis_unit_type: ClassVar[AnalysisUnitType] = "site"
    calls = 0
    last_worker_count = None

    def analyze_batch(
        self,
        units: list[str],
        *,
        n_workers: int,
    ) -> Iterable[dict[str, Scalar]]:
        type(self).calls += 1
        type(self).last_worker_count = n_workers
        return [{"site_id": unit, "value": len(units)} for unit in units]


class BatchStep(FakeAnalysisStep):
    analysis_cls = RecordingBatch

    def analysis_kwargs(self, args):
        return {}


def _args(tmp_path, **outputs):
    return Namespace(
        analysis_output=outputs.get("analysis_output", tmp_path / "analysis.csv"),
        doubled_output=tmp_path / "doubled.csv",
        summary_output=tmp_path / "summary.json",
        value=7,
        n_workers=3,
    )


def test_analysis_step_writes_complete_rows_and_passes_allocated_workers(tmp_path):
    args = _args(tmp_path)

    assert FakeAnalysisStep().run_from_args(args) == 0
    assert FakeAnalysisStep.analysis_output.file_type.read(args.analysis_output) == [
        {"site_id": "site-1", "value": 7}
    ]
    assert FakeAnalysis.last_worker_count == 3


def test_analysis_step_can_write_non_tabular_results(tmp_path):
    step = JsonAnalysisStep()
    validate_component("step", step)
    output = tmp_path / "results.json"
    args = Namespace(json_output=output, n_workers=2)

    assert step.run_from_args(args) == 0
    assert step.json_output.file_type.read(output) == {
        "values": ["SITE-1", "SITE-2"]
    }


def test_analysis_step_writes_header_for_empty_results(tmp_path):
    args = _args(tmp_path)
    assert EmptyAnalysisStep().run_from_args(args) == 0
    assert FakeAnalysisStep.analysis_output.file_type.read(args.analysis_output) == []


def test_analysis_step_requires_class_and_units(tmp_path):
    args = _args(tmp_path)
    with pytest.raises(RuntimeError, match="analysis_cls"):
        MissingAnalysisClassStep().run_from_args(args)
    with pytest.raises(NotImplementedError, match=r"analysis_units\(\)"):
        MissingAnalysisUnitsStep().run_from_args(args)


def test_analysis_step_rejects_invalid_context_kwargs(tmp_path):
    with pytest.raises(TypeError, match=r"analysis_kwargs\(\).*mapping"):
        InvalidAnalysisKwargsStep().run_from_args(_args(tmp_path))


def test_csv_contract_rejects_incomplete_analysis_row(tmp_path):
    args = _args(tmp_path)
    with pytest.raises(ValueError, match="missing: value"):
        MissingColumnStep().run_from_args(args)
    assert not args.analysis_output.exists()


def test_analysis_step_writes_multiple_outputs(tmp_path):
    args = _args(tmp_path)
    assert MultiOutputAnalysisStep().run_from_args(args) == 0
    assert MultiOutputAnalysisStep.doubled_output.file_type.read(
        args.doubled_output
    ) == [{"site_id": "site-1", "double_value": 14}]
    assert MultiOutputAnalysisStep.summary_output.file_type.read(
        args.summary_output
    ) == {"site_count": 1, "worker_count": 3}


@pytest.mark.parametrize(
    "step,match",
    [
        (MissingAdditionalOutputValueStep, "missing: doubled"),
        (InvalidAdditionalOutputValuesStep, r"additional_output_values\(\).*mapping"),
        (UnexpectedAdditionalOutputValueStep, "unexpected: unexpected"),
    ],
)
def test_additional_output_contract_rejects_invalid_values(
    tmp_path, step, match
):
    args = _args(tmp_path)
    with pytest.raises((TypeError, ValueError), match=match):
        step().run_from_args(args)
    assert not args.analysis_output.exists()


def test_analysis_step_accepts_composite_indexes_and_multiple_rows(tmp_path):
    output = tmp_path / "pairs.csv"
    args = _args(tmp_path, analysis_output=output)

    assert PairAnalysisStep().run_from_args(args) == 0
    assert PairAnalysisStep.analysis_output.file_type.read(output) == [
        {"therapeutic_id": "t1", "site_id": "site-1", "value": 1},
        {"therapeutic_id": "t2", "site_id": "site-1", "value": 2},
    ]


def test_csv_contract_rejects_duplicate_composite_index(tmp_path):
    args = _args(tmp_path, analysis_output=tmp_path / "pairs.csv")
    with pytest.raises(ValueError, match="duplicate index"):
        DuplicatePairStep().run_from_args(args)
    assert not args.analysis_output.exists()


def test_batch_step_passes_worker_count_to_backend_once(tmp_path):
    args = _args(tmp_path)
    RecordingBatch.calls = 0
    assert BatchStep().run_from_args(args) == 0
    assert RecordingBatch.calls == 1
    assert BatchStep.analysis_output.file_type.read(args.analysis_output) == [
        {"site_id": "site-1", "value": 1}
    ]
    assert RecordingBatch.last_worker_count == 3
    assert "--n-workers" in BatchStep().build_parser().format_help()
