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
        "--quiet",
        "--no-compute-checksum",
        str(cwl_path),
        str(job_path),
    ]
    assert mock_run.call_args.kwargs["stdout"].name == str(
        tmp_path / "cwl-output.json"
    )
    assert outdir.is_dir()


def test_toil_executor_can_stream_worker_output(tmp_path):
    completed = subprocess.CompletedProcess(args=[], returncode=0)

    with patch("ASOkai._cwl.executors.subprocess.run", return_value=completed) as mock_run:
        ToilExecutor(capture_worker_output=False).run(
            tmp_path / "run.cwl",
            tmp_path / "job.yml",
            tmp_path / "out",
        )

    argv = mock_run.call_args.args[0]
    assert "--disableWorkerOutputCapture" in argv


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
        "--quiet",
        "--no-compute-checksum",
        "--write-summary",
        str(tmp_path / "cwl-output.json"),
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
    ("executor", "extra_args"),
    [
        pytest.param(
            ToilExecutor(extra_args=["--clean", "always"]),
            ["--clean", "always"],
            id="toil",
        ),
        pytest.param(
            CwlToolExecutor(extra_args=["--timestamps"]),
            ["--timestamps"],
            id="cwltool",
        ),
    ],
)
def test_executor_includes_extra_args(tmp_path, executor, extra_args):
    completed = subprocess.CompletedProcess(args=[], returncode=0)
    cwl_path = tmp_path / "run.cwl"
    job_path = tmp_path / "job.yml"
    outdir = tmp_path / "out"

    with patch("ASOkai._cwl.executors.subprocess.run", return_value=completed) as mock_run:
        executor.run(cwl_path, job_path, outdir)

    argv = mock_run.call_args.args[0]
    start = argv.index(extra_args[0])
    assert argv[start : start + len(extra_args)] == extra_args


@pytest.mark.parametrize(
    "executor",
    [ToilExecutor(verbose=True), CwlToolExecutor(verbose=True)],
)
def test_verbose_executor_keeps_engine_logging_enabled(tmp_path, executor):
    completed = subprocess.CompletedProcess(args=[], returncode=0)

    with patch("ASOkai._cwl.executors.subprocess.run", return_value=completed) as mock_run:
        executor.run(
            tmp_path / "run.cwl",
            tmp_path / "job.yml",
            tmp_path / "out",
        )

    argv = mock_run.call_args.args[0]
    assert "--quiet" not in argv
    assert "--no-compute-checksum" in argv
