"""
Filename: src/pipeline/executors.py
Description: Execution backends for pipeline CWL documents.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

import json
import logging
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

logger = logging.getLogger(__name__)


class Executor(Protocol):
    """Execution backend for CWL documents."""

    def run(self, cwl_path: str, inputs: dict, outdir: Path) -> None:
        """Run a CWL document with the provided inputs."""
        ...


@dataclass
class ToilExecutor:
    """Default CWL execution backend using toil-cwl-runner."""

    extra_args: list[str] = field(default_factory=list)

    def run(self, cwl_path: str, inputs: dict, outdir: Path) -> None:
        """Invoke toil-cwl-runner as a subprocess."""
        outdir.mkdir(parents=True, exist_ok=True)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(inputs, f)
            inputs_file = f.name

        cmd = ["toil-cwl-runner", "--outdir", str(outdir)]
        cmd.extend(self.extra_args)
        cmd.extend([cwl_path, inputs_file])
        logger.debug("Running: %s", " ".join(cmd))
        result = subprocess.run(cmd)
        if result.returncode != 0:
            raise RuntimeError(
                f"toil-cwl-runner failed for {cwl_path} (exit {result.returncode})"
            )
