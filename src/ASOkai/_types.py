#!/usr/bin/env python
"""
Filename: src/ASOkai/_types.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Version: 0.1.1
Description: Shared types used throughout ASOkai.
License: LGPL-3.0-or-later
"""
from typing import Literal, TypeAlias


Scalar: TypeAlias = str | int | float | bool | None
Strand: TypeAlias = Literal["+", "-"]
TargetRegion: TypeAlias = Literal[
    "exonic_only",
    "pre-mrna",
    "transcriptomic",
]

__all__ = [
    "Scalar",
    "Strand",
    "TargetRegion",
]
