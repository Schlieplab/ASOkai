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
from typing import ClassVar, Protocol, runtime_checkable

_RUNNABLE_NAME_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")


def is_valid_runnable_name(value: object) -> bool:
    """Return whether a value can identify one pipeline unit or run segment."""
    return type(value) is str and _RUNNABLE_NAME_PATTERN.fullmatch(value) is not None


@runtime_checkable
class Runnable(Protocol):
    """Shared identity for every named pipeline unit or CLI collection."""

    name: ClassVar[str]
    description: ClassVar[str]
