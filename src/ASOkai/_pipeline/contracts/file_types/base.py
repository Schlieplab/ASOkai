#!/usr/bin/env python
"""
Filename: src/ASOkai/_pipeline/contracts/file_types/base.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Version: 0.1.1
Description: Contract for files whose contents ASOkai does not interpret.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class FileType:
    """An opaque file whose step argument remains a filesystem path."""

    media_type: str = "application/octet-stream"
    format_name: str = "Opaque file"

    def __post_init__(self) -> None:
        if type(self.media_type) is not str or not self.media_type.strip():
            raise ValueError("FileType.media_type must be a non-blank string.")
        if type(self.format_name) is not str or not self.format_name.strip():
            raise ValueError("FileType.format_name must be a non-blank string.")

    def read(self, path: str | Path) -> Any:
        """Return an opaque input as a path without interpreting its contents."""
        return Path(path)

    def validate(self, path: str | Path) -> None:
        """Validate an opaque file, which has no content-level contract."""
        if not isinstance(path, (str, Path)):
            raise TypeError("An opaque file value must be a filesystem path.")

    def loads(
        self,
        content: str,
        *,
        source: str = "<string>",
    ) -> Any:
        """Reject text decoding for an opaque file type."""
        raise TypeError(f"{type(self).__name__} does not decode text.")

    def dumps(self, value: Any) -> str:
        """Reject text encoding for an opaque file type."""
        raise TypeError(f"{type(self).__name__} does not encode text.")

    def write(self, path: str | Path, value: Any) -> None:
        """Reject direct writing for an opaque file type."""
        raise TypeError(f"{type(self).__name__} does not write values.")
