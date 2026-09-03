#!/usr/bin/env python
"""
Filename: tests/unit/test_executors.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Tests for pipeline execution backends.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

import subprocess
from unittest.mock import patch

import pytest

from ASOkai._cwl.executors import CwlToolExecutor, ToilExecutor


def test_toil_executor_invokes_toil_cwl_runner(tmp_path):
    completed = subprocess.CompletedProcess(args=[], returncode=0)
    cwl_path = tmp_path / "run.cwl"
    job_path = tmp_path / "job.yml"
    outdir = tmp_path / "out"

    with patch("ASOkai._cwl.executors.subprocess.run", return_value=completed) as mock_run:
        ToilExecutor().run(cwl_path, job_path, outdir)

    assert mock_run.call_args.args[0] == [
        "toil-cwl-runner",
        "--outdir",
        str(outdir),
        "--disableWorkerOutputCapture",
        str(cwl_path),
        str(job_path),
    ]
    assert outdir.is_dir()


def test_toil_executor_can_capture_worker_output(tmp_path):
    completed = subprocess.CompletedProcess(args=[], returncode=0)

    with patch("ASOkai._cwl.executors.subprocess.run", return_value=completed) as mock_run:
        ToilExecutor(capture_worker_output=True).run(
            tmp_path / "run.cwl",
            tmp_path / "job.yml",
            tmp_path / "out",
        )

    argv = mock_run.call_args.args[0]
    assert "--disableWorkerOutputCapture" not in argv


def test_cwltool_executor_invokes_cwltool(tmp_path):
    completed = subprocess.CompletedProcess(args=[], returncode=0)
    cwl_path = tmp_path / "run.cwl"
    job_path = tmp_path / "job.yml"
    outdir = tmp_path / "out"

    with patch("ASOkai._cwl.executors.subprocess.run", return_value=completed) as mock_run:
        CwlToolExecutor().run(cwl_path, job_path, outdir)

    assert mock_run.call_args.args[0] == [
        "cwltool",
        "--outdir",
        str(outdir),
        str(cwl_path),
        str(job_path),
    ]
    assert outdir.is_dir()


@pytest.mark.parametrize(
    ("executor", "executable"),
    [
        pytest.param(ToilExecutor(), "toil-cwl-runner", id="toil"),
        pytest.param(CwlToolExecutor(), "cwltool", id="cwltool"),
    ],
)
def test_executor_raises_on_nonzero_exit(tmp_path, executor, executable):
    failed = subprocess.CompletedProcess(args=[], returncode=7)

    with patch("ASOkai._cwl.executors.subprocess.run", return_value=failed):
        with pytest.raises(RuntimeError, match=rf"{executable} failed.*exit 7"):
            executor.run(
                tmp_path / "run.cwl",
                tmp_path / "job.yml",
                tmp_path / "out",
            )


@pytest.mark.parametrize(
    ("executor", "expected_args"),
    [
        pytest.param(
            ToilExecutor(extra_args=["--clean", "always"]),
            ["--disableWorkerOutputCapture", "--clean", "always"],
            id="toil",
        ),
        pytest.param(
            CwlToolExecutor(extra_args=["--timestamps"]),
            ["--timestamps"],
            id="cwltool",
        ),
    ],
)
def test_executor_includes_extra_args(tmp_path, executor, expected_args):
    completed = subprocess.CompletedProcess(args=[], returncode=0)
    cwl_path = tmp_path / "run.cwl"
    job_path = tmp_path / "job.yml"
    outdir = tmp_path / "out"

    with patch("ASOkai._cwl.executors.subprocess.run", return_value=completed) as mock_run:
        executor.run(cwl_path, job_path, outdir)

    assert mock_run.call_args.args[0] == [
        executor.runner_name,
        "--outdir",
        str(outdir),
        *expected_args,
        str(cwl_path),
        str(job_path),
    ]
