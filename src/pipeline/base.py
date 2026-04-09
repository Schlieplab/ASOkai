"""
Filename: src/ASOkai/pipeline/base.py
Description: Base protocol that all steps, tasks, and workflows must implement.
             Plugin authors implement this interface to extend ASOkai.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class Step(Protocol):
    """Contract for a pipeline step."""

    name: str
    description: str
    dependencies: list[str]
    config_map: dict[str, str]

    @property
    def cwl_path(self) -> str:
        """Path to the CWL file for this step."""
        ...

    def outdir(self, config: dict) -> Path:
        """
        Directory where Toil should stage this step's outputs.
        Passed as --outdir to toil-cwl-runner.
        """
        ...

    def output_paths(self, config: dict) -> dict[str, Path]:
        """Return the expected output paths derived from config."""
        ...

    def outputs_exist(self, config: dict) -> bool:
        """Return True if all outputs already exist on disk."""
        ...

    def cleanup(self, config: dict) -> None:
        """Optional: clean up outputs before a forced re-run."""
        ...
