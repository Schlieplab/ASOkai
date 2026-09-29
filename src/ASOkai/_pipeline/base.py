#!/usr/bin/env python
"""
Filename: src/ASOkai/_pipeline/base.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Shared protocol for named pipeline units.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, ClassVar, Protocol, runtime_checkable

if TYPE_CHECKING:
    from ASOkai._pipeline.steps.base import Step
    from ASOkai._pipeline.tasks.base import Task

_RUNNABLE_NAME_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")


def is_valid_runnable_name(value: object) -> bool:
    """Return whether a value can identify one pipeline unit or run segment."""
    return type(value) is str and _RUNNABLE_NAME_PATTERN.fullmatch(value) is not None


@runtime_checkable
class Runnable(Protocol):
    """Shared identity for every named pipeline unit or CLI collection."""

    name: ClassVar[str]
    description: ClassVar[str]


def flatten_workflow_members(
    runnable: Runnable,
    seen_workflows: frozenset[str] = frozenset(),
) -> list[Step | Task]:
    """Flatten nested workflows into steps and intact tasks."""
    from ASOkai._pipeline.steps.base import Step
    from ASOkai._pipeline.tasks.base import Task
    from ASOkai._pipeline.workflows.base import Workflow

    if isinstance(runnable, Workflow):
        if runnable.name in seen_workflows:
            raise ValueError(f"Workflow '{runnable.name}' participates in a cycle.")
        seen = seen_workflows | {runnable.name}
        members: list[Step | Task] = []
        for member in runnable.members:
            members.extend(flatten_workflow_members(member, seen))
        return members
    if isinstance(runnable, Task):
        return [runnable]
    if isinstance(runnable, Step):
        return [runnable]
    raise TypeError(f"Unsupported runnable type: {type(runnable).__name__!r}.")


def expand_runnable_steps(
    runnable: Runnable,
    seen_workflows: frozenset[str] = frozenset(),
) -> list[Step]:
    """Expand one runnable into its ordered endpoint steps."""
    from ASOkai._pipeline.steps.base import Step

    steps: list[Step] = []
    for member in flatten_workflow_members(runnable, seen_workflows):
        if isinstance(member, Step):
            steps.append(member)
        else:
            steps.extend(member.steps)
    return steps
