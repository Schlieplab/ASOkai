"""
Execution backends for CWL documents.
"""

from __future__ import annotations

import json
import logging
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar, Protocol

logger = logging.getLogger(__name__)


class Executor(Protocol):
    """Execution backend for CWL documents."""

    runner_name: ClassVar[str]

    def run(self, cwl_path: str, inputs: dict, outdir: Path) -> None:
        """Run a CWL document with the provided inputs."""
        ...


@dataclass
class ToilExecutor:
    """Default CWL execution backend using toil-cwl-runner."""

    runner_name: ClassVar[str] = "toil-cwl-runner"
    extra_args: list[str] = field(default_factory=list)
    realtime_output: bool = True

    def run(self, cwl_path: str, inputs: dict, outdir: Path) -> None:
        """Invoke toil-cwl-runner as a subprocess."""
        outdir.mkdir(parents=True, exist_ok=True)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(inputs, f)
            inputs_file = f.name

        cmd = ["toil-cwl-runner", "--outdir", str(outdir)]
        if self.realtime_output:
            cmd.append("--disableWorkerOutputCapture")
        cmd.extend(self.extra_args)
        cmd.extend([cwl_path, inputs_file])
        logger.debug("Running: %s", " ".join(cmd))
        result = subprocess.run(cmd)
        if result.returncode != 0:
            raise RuntimeError(
                f"toil-cwl-runner failed for {cwl_path} (exit {result.returncode})"
            )


@dataclass
class CwlToolExecutor:
    """Local CWL execution backend using cwltool."""

    runner_name: ClassVar[str] = "cwltool"
    extra_args: list[str] = field(default_factory=list)

    def run(self, cwl_path: str, inputs: dict, outdir: Path) -> None:
        """Invoke cwltool as a subprocess."""
        outdir.mkdir(parents=True, exist_ok=True)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(inputs, f)
            inputs_file = f.name

        cmd = ["cwltool", "--outdir", str(outdir)]
        cmd.extend(self.extra_args)
        cmd.extend([cwl_path, inputs_file])
        logger.debug("Running: %s", " ".join(cmd))
        result = subprocess.run(cmd)
        if result.returncode != 0:
            raise RuntimeError(
                f"cwltool failed for {cwl_path} (exit {result.returncode})"
            )
