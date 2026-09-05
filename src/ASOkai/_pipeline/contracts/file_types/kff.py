#!/usr/bin/env python
"""
Filename: src/ASOkai/_pipeline/contracts/file_types/kff.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Contract for K-mer File Format index files.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .base import FileType


_KFF_MAGIC = b"KFF"


@dataclass(frozen=True, init=False)
class KffFile(FileType):
    """A KFF index with the required opening and closing markers."""

    def __init__(self) -> None:
        object.__setattr__(self, "media_type", "application/octet-stream")
        object.__setattr__(self, "format_name", "KFF k-mer index")

    def read(self, path: str | Path) -> Path:
        """Return a KFF input path without loading the index."""
        return Path(path)

    def validate(self, path: str | Path) -> None:
        """Require the framing markers of a complete KFF file."""
        super().validate(path)
        source = Path(path)
        if source.stat().st_size < 2 * len(_KFF_MAGIC):
            raise ValueError(f"Invalid KFF file {source}: file is too short.")
        with source.open("rb") as stream:
            opening = stream.read(len(_KFF_MAGIC))
            stream.seek(-len(_KFF_MAGIC), 2)
            closing = stream.read(len(_KFF_MAGIC))
        if opening != _KFF_MAGIC or closing != _KFF_MAGIC:
            raise ValueError(
                f"Invalid KFF file {source}: missing KFF framing markers."
            )
