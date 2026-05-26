"""
Filename: src/pipeline/base.py
Description: Base protocols that steps, tasks, and workflows must implement.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class Runnable(Protocol):
    """
    Shared contract for every named pipeline unit (step, task, or workflow).
    """

    name: str
    description: str

    def output_paths(self, config: dict) -> dict[str, Path]:
        ...

    def outputs_exist(self, config: dict) -> bool:
        ...

    def cleanup(self, config: dict) -> None:
        ...


@runtime_checkable
class Step(Runnable, Protocol):
    """Atomic pipeline unit backed by a static CWL file."""

    dependencies: list[str]
    config_map: dict[str, str]
    input_overrides: dict[str, str]
    cli_module: str

    @property
    def cwl_path(self) -> str:
        """Path to the static CWL file for this step."""
        ...

    def outdir(self, config: dict) -> Path:
        """Directory passed to the CWL executor for this step's outputs."""
        ...


@runtime_checkable
class Task(Runnable, Protocol):
    """Ordered composition of Steps."""

    steps: list[Step]


@runtime_checkable
class Workflow(Runnable, Protocol):
    """
    Ordered composition of Runnables (Steps, Tasks, or nested Workflows).

    CWL is generated at runtime by recursively flattening ``members`` to Steps.
    """

    members: list[Runnable]
