#!/usr/bin/env python
"""
Filename: src/ASOkai/_pipeline/contracts/file_types/fasta.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Contract for a FASTA reference file.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .base import FileType


@dataclass(frozen=True, init=False)
class FastaFile(FileType):
    """A plain or gzipped FASTA path passed to external tools."""

    gzip: bool | None = False

    def __init__(self, gzip: bool | None = False) -> None:
        if gzip is not None and type(gzip) is not bool:
            raise TypeError("FastaFile.gzip must be a boolean or None.")
        object.__setattr__(self, "media_type", "application/x-fasta")
        format_name = {
            True: "gzip-compressed FASTA reference",
            False: "plain FASTA reference",
            None: "plain or gzip-compressed FASTA reference",
        }[gzip]
        object.__setattr__(self, "format_name", format_name)
        object.__setattr__(self, "gzip", gzip)

    def read(self, path: str | Path) -> Path:
        return Path(path)

    def validate(self, path: str | Path) -> None:
        super().validate(path)
        if not Path(path).is_file():
            raise ValueError(f"FASTA reference is not a file: {path}.")
