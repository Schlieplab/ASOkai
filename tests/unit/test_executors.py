"""Tests for pipeline execution backends."""
from __future__ import annotations

import subprocess
from unittest.mock import patch

import pytest

from ASOkai._pipeline.executors import CwlToolExecutor, ToilExecutor


def test_toil_executor_invokes_toil_cwl_runner(tmp_path):
    completed = subprocess.CompletedProcess(args=[], returncode=0)

    with patch("ASOkai._pipeline.executors.subprocess.run", return_value=completed) as mock_run:
        ToilExecutor().run("workflow.cwl", {"x": 1}, tmp_path / "out")

    argv = mock_run.call_args.args[0]
    assert argv[:4] == [
        "toil-cwl-runner",
        "--outdir",
        str(tmp_path / "out"),
        "--disableWorkerOutputCapture",
    ]
    assert argv[4] == "workflow.cwl"
    assert argv[5].endswith(".json")


def test_toil_executor_raises_on_nonzero_exit(tmp_path):
    failed = subprocess.CompletedProcess(args=[], returncode=7)

    with patch("ASOkai._pipeline.executors.subprocess.run", return_value=failed):
        with pytest.raises(RuntimeError, match="exit 7"):
            ToilExecutor().run("workflow.cwl", {}, tmp_path / "out")


def test_toil_executor_includes_extra_args(tmp_path):
    completed = subprocess.CompletedProcess(args=[], returncode=0)

    with patch("ASOkai._pipeline.executors.subprocess.run", return_value=completed) as mock_run:
        ToilExecutor(extra_args=["--clean", "always"]).run(
            "workflow.cwl", {"x": 1}, tmp_path / "out"
        )

    argv = mock_run.call_args.args[0]
    assert argv[:6] == [
        "toil-cwl-runner",
        "--outdir",
        str(tmp_path / "out"),
        "--disableWorkerOutputCapture",
        "--clean",
        "always",
    ]
    assert argv[6] == "workflow.cwl"


def test_toil_executor_can_disable_realtime_output(tmp_path):
    completed = subprocess.CompletedProcess(args=[], returncode=0)

    with patch("ASOkai._pipeline.executors.subprocess.run", return_value=completed) as mock_run:
        ToilExecutor(realtime_output=False).run("workflow.cwl", {}, tmp_path / "out")

    argv = mock_run.call_args.args[0]
    assert "--disableWorkerOutputCapture" not in argv


def test_cwltool_executor_invokes_cwltool(tmp_path):
    completed = subprocess.CompletedProcess(args=[], returncode=0)

    with patch("ASOkai._pipeline.executors.subprocess.run", return_value=completed) as mock_run:
        CwlToolExecutor().run("workflow.cwl", {"x": 1}, tmp_path / "out")

    argv = mock_run.call_args.args[0]
    assert argv[:3] == ["cwltool", "--outdir", str(tmp_path / "out")]
    assert argv[3] == "workflow.cwl"
    assert argv[4].endswith(".json")


def test_cwltool_executor_raises_on_nonzero_exit(tmp_path):
    failed = subprocess.CompletedProcess(args=[], returncode=7)

    with patch("ASOkai._pipeline.executors.subprocess.run", return_value=failed):
        with pytest.raises(RuntimeError, match="cwltool failed.*exit 7"):
            CwlToolExecutor().run("workflow.cwl", {}, tmp_path / "out")


def test_cwltool_executor_includes_extra_args(tmp_path):
    completed = subprocess.CompletedProcess(args=[], returncode=0)

    with patch("ASOkai._pipeline.executors.subprocess.run", return_value=completed) as mock_run:
        CwlToolExecutor(extra_args=["--timestamps"]).run(
            "workflow.cwl", {"x": 1}, tmp_path / "out"
        )

    argv = mock_run.call_args.args[0]
    assert argv[:4] == ["cwltool", "--outdir", str(tmp_path / "out"), "--timestamps"]
    assert argv[4] == "workflow.cwl"
