#!/usr/bin/env python
"""
Filename: src/ASOkai/_pipeline/base.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Version: 0.1.1
Description: Shared protocol for named pipeline units.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, ClassVar, Protocol, runtime_checkable

if TYPE_CHECKING:
    from ASOkai._pipeline.steps.base import Step

_RUNNABLE_NAME_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")


def is_valid_runnable_name(value: object) -> bool:
    """Return whether a value can identify one pipeline unit or run segment."""
    return type(value) is str and _RUNNABLE_NAME_PATTERN.fullmatch(value) is not None


@runtime_checkable
class Runnable(Protocol):
    """Shared identity for every named pipeline unit or CLI collection."""

    name: ClassVar[str]
    description: ClassVar[str]


def expand_runnable_steps(
    runnable: Runnable,
    seen_workflows: frozenset[str] = frozenset(),
) -> list[Step]:
    """Expand one runnable into its ordered endpoint steps."""
    from ASOkai._pipeline.steps.base import Step
    from ASOkai._pipeline.tasks.base import Task
    from ASOkai._pipeline.workflows.base import Workflow

    if isinstance(runnable, Workflow):
        if runnable.name in seen_workflows:
            raise ValueError(f"Workflow '{runnable.name}' participates in a cycle.")
        seen = seen_workflows | {runnable.name}
        steps: list[Step] = []
        for member in runnable.members:
            steps.extend(expand_runnable_steps(member, seen))
        return steps
    if isinstance(runnable, Task):
        return list(runnable.steps)
    if isinstance(runnable, Step):
        return [runnable]
    raise TypeError(f"Unsupported runnable type: {type(runnable).__name__!r}.")
