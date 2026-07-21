#!/usr/bin/env python
"""Tests for AnalysisStep template execution."""

import json
from argparse import Namespace

import pytest

from ASOkai._cwl.spec import OutputParam, StepSpec
from ASOkai._pipeline.base import AnalysisStep


class FakeAnalysis:
    last_process_count = None

    def __init__(self, value, n_processes):
        self.value = value
        type(self).last_process_count = n_processes

    def run(self):
        return {"site-1": {"value": self.value}}


class FakeAnalysisStep(AnalysisStep):
    name = "fake-analysis"
    description = "Fake analysis."
    analysis_cls = FakeAnalysis
    cli_module = "tests.fake"
    dependencies = []
    spec = StepSpec(
        outputs=[OutputParam("analysis", temp_filename="analysis.json")]
    )

    def outdir(self, config):
        return config["outdir"]

    def output_paths(self, config):
        return {}

    def outputs_exist(self, config):
        return False

    def cleanup(self, config):
        pass

    def load_analysis_inputs(self, args):
        return {"value": args.value}

    def analysis_kwargs(self, args, inputs):
        return {"value": inputs["value"]}

    def analysis_metadata(self, args, inputs):
        return {"analysis": self.name, "value": inputs["value"]}


class MissingAnalysisClassStep(FakeAnalysisStep):
    analysis_cls = None


def test_analysis_step_run_from_args_writes_metadata_and_results(tmp_path):
    output = tmp_path / "analysis.json"
    args = Namespace(analysis_output=output, value=7, n_processes=3)

    result = FakeAnalysisStep().run_from_args(args)

    assert result == 0
    assert json.loads(output.read_text()) == {
        "analysis": "fake-analysis",
        "value": 7,
        "results": {"site-1": {"value": 7}},
    }
    assert FakeAnalysis.last_process_count == 3


def test_analysis_step_requires_analysis_class(tmp_path):
    args = Namespace(
        analysis_output=tmp_path / "analysis.json",
        value=7,
        n_processes=1,
    )

    with pytest.raises(RuntimeError, match="analysis_cls"):
        MissingAnalysisClassStep().run_from_args(args)
