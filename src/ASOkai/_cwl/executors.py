#!/usr/bin/env python
"""
Filename: src/ASOkai/_cwl/executors.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Execution backends for CWL documents.
License: LGPL-3.0-or-later
"""
from __future__ import annotations

from collections.abc import Sequence
import logging
import shlex
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar, Protocol

logger = logging.getLogger(__name__)


class Executor(Protocol):
    """Execution backend for CWL documents."""

    runner_name: ClassVar[str]

    def run(self, cwl_path: Path, job_path: Path, outdir: Path) -> None:
        """Run a CWL document with the provided job document."""
        ...


def _run_cwl_runner(
    executable: str,
    cwl_path: Path,
    job_path: Path,
    outdir: Path,
    extra_args: Sequence[str],
    *,
    stdout_path: Path | None = None,
) -> None:
    """Invoke one CWL runner and translate a failed exit into a runtime error."""
    outdir.mkdir(parents=True, exist_ok=True)
    command = [
        executable,
        "--outdir",
        str(outdir),
        *extra_args,
        str(cwl_path),
        str(job_path),
    ]
    logger.debug("Running: %s", shlex.join(command))
    if stdout_path is None:
        result = subprocess.run(command)
    else:
        with stdout_path.open("w", encoding="utf-8") as stdout:
            result = subprocess.run(command, stdout=stdout)
    if result.returncode != 0:
        raise RuntimeError(
            f"{executable} failed for {cwl_path} (exit {result.returncode})"
        )


@dataclass
class ToilExecutor:
    """CWL execution backend using toil-cwl-runner."""

    runner_name: ClassVar[str] = "toil-cwl-runner"
    extra_args: list[str] = field(default_factory=list)
    capture_worker_output: bool = True
    verbose: bool = False

    def run(self, cwl_path: Path, job_path: Path, outdir: Path) -> None:
        """Invoke toil-cwl-runner as a subprocess."""
        runner_args = [] if self.verbose else ["--quiet"]
        runner_args.append("--no-compute-checksum")
        if not self.capture_worker_output:
            runner_args.append("--disableWorkerOutputCapture")
        runner_args.extend(self.extra_args)
        _run_cwl_runner(
            self.runner_name,
            cwl_path,
            job_path,
            outdir,
            runner_args,
            stdout_path=cwl_path.parent / "cwl-output.json",
        )


@dataclass
class CwlToolExecutor:
    """Local CWL execution backend using cwltool."""

    runner_name: ClassVar[str] = "cwltool"
    extra_args: list[str] = field(default_factory=list)
    verbose: bool = False

    def run(self, cwl_path: Path, job_path: Path, outdir: Path) -> None:
        """Invoke cwltool as a subprocess."""
        summary_path = cwl_path.parent / "cwl-output.json"
        runner_args = [] if self.verbose else ["--quiet"]
        runner_args.extend(
            [
                "--no-compute-checksum",
                "--write-summary",
                str(summary_path),
                *self.extra_args,
            ]
        )
        _run_cwl_runner(
            self.runner_name,
            cwl_path,
            job_path,
            outdir,
            runner_args,
        )
