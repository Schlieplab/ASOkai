#!/usr/bin/env python
"""
Filename: src/ASOkai/_cwl/executors.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Version: 0.1.1
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
    result = subprocess.run(command)
    if result.returncode != 0:
        raise RuntimeError(
            f"{executable} failed for {cwl_path} (exit {result.returncode})"
        )


@dataclass
class ToilExecutor:
    """CWL execution backend using toil-cwl-runner."""

    runner_name: ClassVar[str] = "toil-cwl-runner"
    extra_args: list[str] = field(default_factory=list)
    capture_worker_output: bool = False

    def run(self, cwl_path: Path, job_path: Path, outdir: Path) -> None:
        """Invoke toil-cwl-runner as a subprocess."""
        runner_args = []
        if not self.capture_worker_output:
            runner_args.append("--disableWorkerOutputCapture")
        runner_args.extend(self.extra_args)
        _run_cwl_runner(
            self.runner_name,
            cwl_path,
            job_path,
            outdir,
            runner_args,
        )


@dataclass
class CwlToolExecutor:
    """Local CWL execution backend using cwltool."""

    runner_name: ClassVar[str] = "cwltool"
    extra_args: list[str] = field(default_factory=list)

    def run(self, cwl_path: Path, job_path: Path, outdir: Path) -> None:
        """Invoke cwltool as a subprocess."""
        _run_cwl_runner(
            self.runner_name,
            cwl_path,
            job_path,
            outdir,
            self.extra_args,
        )
