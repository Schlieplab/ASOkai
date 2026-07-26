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

from pathlib import Path
from typing import ClassVar, Protocol, runtime_checkable


@runtime_checkable
class Runnable(Protocol):
    """Shared contract for every named pipeline unit or CLI collection."""

    name: ClassVar[str]
    description: ClassVar[str]

    def output_paths(self, config: dict) -> dict[str, Path]:
        ...

    def outputs_exist(self, config: dict) -> bool:
        ...

    def cleanup(self, config: dict) -> None:
        ...
