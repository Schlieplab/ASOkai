"""Tests for pipeline execution backends."""
from __future__ import annotations

import subprocess
from unittest.mock import patch

import pytest

from pipeline.executors import ToilExecutor


def test_toil_executor_invokes_toil_cwl_runner(tmp_path):
    completed = subprocess.CompletedProcess(args=[], returncode=0)

    with patch("pipeline.executors.subprocess.run", return_value=completed) as mock_run:
        ToilExecutor().run("workflow.cwl", {"x": 1}, tmp_path / "out")

    argv = mock_run.call_args.args[0]
    assert argv[:3] == ["toil-cwl-runner", "--outdir", str(tmp_path / "out")]
    assert argv[3] == "workflow.cwl"
    assert argv[4].endswith(".json")


def test_toil_executor_raises_on_nonzero_exit(tmp_path):
    failed = subprocess.CompletedProcess(args=[], returncode=7)

    with patch("pipeline.executors.subprocess.run", return_value=failed):
        with pytest.raises(RuntimeError, match="exit 7"):
            ToilExecutor().run("workflow.cwl", {}, tmp_path / "out")


def test_toil_executor_includes_extra_args(tmp_path):
    completed = subprocess.CompletedProcess(args=[], returncode=0)

    with patch("pipeline.executors.subprocess.run", return_value=completed) as mock_run:
        ToilExecutor(extra_args=["--clean", "always"]).run(
            "workflow.cwl", {"x": 1}, tmp_path / "out"
        )

    argv = mock_run.call_args.args[0]
    assert argv[:5] == [
        "toil-cwl-runner",
        "--outdir",
        str(tmp_path / "out"),
        "--clean",
        "always",
    ]
    assert argv[5] == "workflow.cwl"
