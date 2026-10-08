#!/usr/bin/env python
"""
Filename: src/ASOkai/_pipeline/contracts/file_types/sam.py
Author: Kian Jalilian
Copyright: 2026, Alexander Schliep
Description: Contract for a SAM alignment file.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .base import FileType


@dataclass(frozen=True, init=False)
class SamFile(FileType):
    """A SAM alignment file passed between aligner and analysis steps."""

    def __init__(self) -> None:
        object.__setattr__(self, "media_type", "text/x-sam")
        object.__setattr__(self, "format_name", "SAM alignments")

    def read(self, path: str | Path) -> Path:
        """Return the alignment path without parsing its records."""
        return Path(path)

    def validate(self, path: str | Path) -> None:
        """Require an existing SAM file."""
        # TODO: Validate the SAM header and records once the format is fixed.
        super().validate(path)
        if not Path(path).is_file():
            raise ValueError(f"SAM alignments are not a file: {path}.")
