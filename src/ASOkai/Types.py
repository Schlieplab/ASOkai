#!/usr/bin/env python
"""
Filename: src/ASOkai/Types.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Shared public types used throughout ASOkai.
License: LGPL-3.0-or-later
"""
from typing import Literal, TypeAlias


#: JSON-compatible scalar used by serialization, configuration, and file contracts.
Scalar: TypeAlias = str | int | float | bool | None
#: Genomic strand orientation.
Strand: TypeAlias = Literal["+", "-"]
#: Region of a target gene from which target sites are constructed.
TargetRegion: TypeAlias = Literal[
    "exonic",
    "pre-mrna",
    "transcriptomic",
]

__all__ = [
    "Scalar",
    "Strand",
    "TargetRegion",
]
