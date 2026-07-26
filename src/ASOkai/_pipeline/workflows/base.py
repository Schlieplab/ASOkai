#!/usr/bin/env python
"""
Filename: src/ASOkai/_pipeline/workflows/base.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Version: 0.1.1
Description: Protocol for named pipeline workflows.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ASOkai._pipeline.base import Runnable


@runtime_checkable
class Workflow(Runnable, Protocol):
    """CLI-level named collection of pipeline units."""

    members: list[Runnable]
