#!/usr/bin/env python
"""Tests for writing standalone CWL job bundles."""
from datetime import datetime
from unittest.mock import patch

from ASOkai._cwl.export import _run_commands, write_cwl_job_bundle
from ASOkai._cwl.generation import GeneratedCwlBundle


def _bundle() -> GeneratedCwlBundle:
    return GeneratedCwlBundle(
        run_cwl="class: Workflow\n",
        publish_cwl="class: CommandLineTool\n",
        output_layout="version: 1\noutputs: []\n",
        step_cwls={"example.cwl": "class: CommandLineTool\n"},
    )


def test_run_commands_accepts_an_arbitrary_runner_executable():
    assert "custom-cwl-runner --outdir /path/to/data run.cwl job.yml" in _run_commands(
        "custom-cwl-runner"
    )


def test_write_cwl_job_bundle_avoids_timestamp_name_collisions(tmp_path):
    fixed_time = datetime(2026, 7, 13, 12, 34, 56)

    with patch("ASOkai._cwl.export.datetime") as datetime_mock:
        datetime_mock.now.return_value = fixed_time
        first = write_cwl_job_bundle(
            bundle=_bundle(),
            inputs={},
            parent_dir=tmp_path,
            label="first",
            runner_name="cwltool",
            name_prefix="asokai-job",
        )
        second = write_cwl_job_bundle(
            bundle=_bundle(),
            inputs={},
            parent_dir=tmp_path,
            label="second",
            runner_name="cwltool",
            name_prefix="asokai-job",
        )

    assert first.name == "asokai-job-20260713-123456"
    assert second.name == "asokai-job-20260713-123456-2"
    assert (first / "run.cwl").exists()
    assert (first / "publish.cwl").exists()
    assert (first / "output-layout.yml").exists()
    assert (first / "steps" / "example.cwl").exists()
    assert (second / "run.cwl").exists()
