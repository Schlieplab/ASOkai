#!/usr/bin/env python
"""
Filename: src/ASOkai/_pipeline/workflows/base.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Protocol for named pipeline workflows.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

from typing import Protocol, Sequence, runtime_checkable

from ASOkai._pipeline.base import Runnable


@runtime_checkable
class Workflow(Runnable, Protocol):
    """CLI-level named collection of pipeline units."""

    @property
    def members(self) -> Sequence[Runnable]:
        """Return the runnable components selected by this workflow."""
        ...
