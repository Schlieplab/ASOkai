#!/usr/bin/env python
"""Tests for AnalysisStep template execution."""

from argparse import Namespace
from typing import Any, cast

import pytest

from ASOkai.Analysis import Analysis
from ASOkai.Plugins import (
    AnalysisStep,
    CsvFile,
    FileOutput,
    JsonFile,
    ScalarParam,
    StepSpec,
)
class FakeAnalysis(Analysis):
    last_process_count = None

    def __init__(self, value, n_processes):
        self.value = value
        type(self).last_process_count = n_processes

    def run(self):
        return {"site-1": {"value": self.value}}

    def analyze(self, site):
        return {"value": self.value}


class FakeAnalysisStep(AnalysisStep):
    name = "fake-analysis"
    description = "Fake analysis."
    analysis_cls = FakeAnalysis
    analysis_output = FileOutput(
        "analysis",
        destination="analysis.csv",
        file_type=CsvFile(
            index={"site_id": str},
            columns={"value": int},
        ),
    )
    spec = StepSpec(
        params=[ScalarParam("value", int)],
        outputs=[analysis_output],
    )

    def analysis_kwargs(self, args):
        return {"value": args.value}


class MissingAnalysisClassStep(FakeAnalysisStep):
    analysis_cls = None


class ConflictingProcessCountStep(FakeAnalysisStep):
    def analysis_kwargs(self, args):
        return {
            "value": args.value,
            "n_processes": 99,
        }


class InvalidAnalysisKwargsStep(FakeAnalysisStep):
    def analysis_kwargs(self, args):
        return cast(Any, None)


class MultiOutputAnalysisStep(AnalysisStep):
    name = "multi-output-analysis"
    description = "Analysis with CSV and JSON outputs."
    analysis_cls = FakeAnalysis
    analysis_output = FileOutput(
        "analysis",
        destination="analysis.csv",
        file_type=CsvFile(
            index={"site_id": str},
            columns={"value": int},
        ),
    )
    doubled_output = FileOutput(
        "doubled",
        destination="doubled.csv",
        file_type=CsvFile(
            index={"site_id": str},
            columns={"double_value": int},
        ),
    )
    summary_output = FileOutput(
        "summary",
        destination="summary.json",
        file_type=JsonFile(),
    )
    spec = StepSpec(
        params=[ScalarParam("value", int)],
        outputs=[analysis_output, doubled_output, summary_output],
    )

    def analysis_kwargs(self, args):
        return {"value": args.value}

    def additional_output_values(self, analysis, results):
        return {
            self.doubled_output: [
                {
                    "site_id": site_id,
                    "double_value": cast(int, values["value"]) * 2,
                }
                for site_id, values in results.items()
            ],
            self.summary_output: {
                "site_count": len(results),
                "process_count": analysis.last_process_count,
            },
        }


class MissingAdditionalOutputValueStep(MultiOutputAnalysisStep):
    def additional_output_values(self, analysis, results):
        return {
            self.summary_output: {"site_count": len(results)},
        }


class InvalidAdditionalOutputValuesStep(MultiOutputAnalysisStep):
    def additional_output_values(self, analysis, results):
        return cast(Any, None)


def test_analysis_step_writes_site_keyed_results_as_csv_rows(tmp_path):
    output = tmp_path / "analysis.csv"
    args = Namespace(analysis_output=output, value=7, n_processes=3)

    result = FakeAnalysisStep().run_from_args(args)

    assert result == 0
    assert FakeAnalysisStep.analysis_output.file_type.read(output) == [
        {
            "site_id": "site-1",
            "value": 7,
        }
    ]
    assert FakeAnalysis.last_process_count == 3


def test_analysis_step_requires_analysis_class(tmp_path):
    args = Namespace(
        analysis_output=tmp_path / "analysis.csv",
        value=7,
        n_processes=1,
    )

    with pytest.raises(RuntimeError, match="analysis_cls"):
        MissingAnalysisClassStep().run_from_args(args)


def test_analysis_step_uses_the_framework_allocated_process_count(tmp_path):
    args = Namespace(
        analysis_output=tmp_path / "analysis.csv",
        value=7,
        n_processes=2,
    )

    ConflictingProcessCountStep().run_from_args(args)

    assert FakeAnalysis.last_process_count == 2


def test_analysis_step_requires_analysis_kwargs_to_be_a_mapping(tmp_path):
    args = Namespace(
        analysis_output=tmp_path / "analysis.csv",
        value=7,
        n_processes=1,
    )

    with pytest.raises(TypeError, match=r"analysis_kwargs\(\).*mapping"):
        InvalidAnalysisKwargsStep().run_from_args(args)


def test_analysis_step_writes_multiple_csv_and_json_outputs(tmp_path):
    analysis_output = tmp_path / "analysis.csv"
    doubled_output = tmp_path / "doubled.csv"
    summary_output = tmp_path / "summary.json"
    args = Namespace(
        analysis_output=analysis_output,
        doubled_output=doubled_output,
        summary_output=summary_output,
        value=7,
        n_processes=3,
    )

    step = MultiOutputAnalysisStep()
    result = step.run_from_args(args)

    assert result == 0
    assert MultiOutputAnalysisStep.analysis_output.file_type.read(analysis_output) == [
        {"site_id": "site-1", "value": 7}
    ]
    assert MultiOutputAnalysisStep.doubled_output.file_type.read(doubled_output) == [
        {"site_id": "site-1", "double_value": 14}
    ]
    assert MultiOutputAnalysisStep.summary_output.file_type.read(summary_output) == {
        "site_count": 1,
        "process_count": 3,
    }


def test_analysis_step_requires_every_additional_output_value(tmp_path):
    args = Namespace(
        analysis_output=tmp_path / "analysis.csv",
        doubled_output=tmp_path / "doubled.csv",
        summary_output=tmp_path / "summary.json",
        value=7,
        n_processes=1,
    )

    with pytest.raises(ValueError, match=r"missing: doubled"):
        MissingAdditionalOutputValueStep().run_from_args(args)

    assert not args.analysis_output.exists()


def test_analysis_step_requires_additional_values_to_be_a_mapping(tmp_path):
    args = Namespace(
        analysis_output=tmp_path / "analysis.csv",
        doubled_output=tmp_path / "doubled.csv",
        summary_output=tmp_path / "summary.json",
        value=7,
        n_processes=1,
    )

    with pytest.raises(TypeError, match=r"additional_output_values\(\).*mapping"):
        InvalidAdditionalOutputValuesStep().run_from_args(args)

    assert not args.analysis_output.exists()
