#!/usr/bin/env python
"""
Filename: src/ASOkai/_pipeline/tasks/base.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Protocol for named collections of pipeline steps.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

from typing import Protocol, Sequence, runtime_checkable

from ASOkai._pipeline.base import Runnable
from ASOkai._pipeline.steps.base import Step


@runtime_checkable
class Task(Runnable, Protocol):
    """CLI-level named collection of Steps."""

    @property
    def steps(self) -> Sequence[Step]:
        """Return the steps selected by this task."""
        ...
