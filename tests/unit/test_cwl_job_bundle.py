#!/usr/bin/env python
"""
Filename: tests/unit/test_cwl_job_bundle.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Version: 0.1.1
Description: Tests for writing standalone CWL job bundles.
License: LGPL-3.0-or-later
"""

from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from ASOkai._cwl.job_bundle import write_cwl_job_bundle
from ASOkai._cwl.generation import GeneratedCwlBundle


def _bundle() -> GeneratedCwlBundle:
    return GeneratedCwlBundle(
        run_cwl="class: Workflow\n",
        publish_cwl="class: CommandLineTool\n",
        output_layout="version: 1\noutputs: []\n",
        step_cwls={"example.cwl": "class: CommandLineTool\n"},
    )


def test_write_cwl_job_bundle_writes_complete_standalone_bundle(tmp_path):
    job_dir = write_cwl_job_bundle(
        bundle=_bundle(),
        inputs={
            "enabled": True,
            "input": {"class": "File", "path": "/machine/input.fa"},
        },
        parent_dir=tmp_path / "jobs",
        label="example workflow",
        runner_name="custom-cwl-runner",
        name_prefix="asokai-job",
    )

    assert job_dir.parent == tmp_path / "jobs"
    assert job_dir.name.startswith("asokai-job-")
    assert (job_dir / "run.cwl").read_text() == "class: Workflow\n"
    assert (job_dir / "publish.cwl").read_text() == (
        "class: CommandLineTool\n"
    )
    assert (job_dir / "output-layout.yml").read_text() == (
        "version: 1\noutputs: []\n"
    )
    assert (job_dir / "steps" / "example.cwl").read_text() == (
        "class: CommandLineTool\n"
    )
    assert yaml.safe_load((job_dir / "job.yml").read_text()) == {
        "enabled": True,
        "input": {"class": "File", "path": "/machine/input.fa"},
    }
    readme = (job_dir / "README.md").read_text()
    assert "prepared ASOkai CWL job bundle for `example workflow`" in readme
    assert "custom-cwl-runner --outdir /path/to/data run.cwl job.yml" in readme
    assert "File inputs can contain absolute paths" in readme
    assert "Files at declared output destinations may be replaced" in readme


def test_write_cwl_job_bundle_avoids_timestamp_name_collisions(tmp_path):
    fixed_time = datetime(2026, 7, 13, 12, 34, 56)

    with patch("ASOkai._cwl.job_bundle.datetime") as datetime_mock:
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
    assert (second / "run.cwl").exists()


def test_write_cwl_job_bundle_removes_incomplete_directory(
    tmp_path,
    monkeypatch,
):
    original_write_text = Path.write_text

    def fail_while_writing_publisher(path, text, **kwargs):
        if path.name == "publish.cwl":
            raise OSError("simulated write failure")
        return original_write_text(path, text, **kwargs)

    monkeypatch.setattr(Path, "write_text", fail_while_writing_publisher)

    with pytest.raises(OSError, match="simulated write failure"):
        write_cwl_job_bundle(
            bundle=_bundle(),
            inputs={},
            parent_dir=tmp_path,
            label="example",
            runner_name="cwltool",
            name_prefix="asokai-job",
        )

    assert list(tmp_path.iterdir()) == []
