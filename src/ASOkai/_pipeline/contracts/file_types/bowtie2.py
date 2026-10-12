#!/usr/bin/env python
"""
Filename: src/ASOkai/_pipeline/contracts/file_types/bowtie2.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Contract for a complete Bowtie 2 index directory.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, Literal

from ASOkai.Utils import Bowtie2ExecutionError, Bowtie2Inspect

from .base import FileType


_PARTS = ("1", "2", "3", "4", "rev.1", "rev.2")


@dataclass(frozen=True, init=False)
class Bowtie2IndexDirectory(FileType):
    """Six small or large Bowtie 2 index files named ``index.*``."""

    cwl_type: ClassVar[Literal["Directory"]] = "Directory"

    def __init__(self) -> None:
        object.__setattr__(self, "media_type", "application/x-directory")
        object.__setattr__(self, "format_name", "Bowtie 2 index directory")

    @staticmethod
    def index_base(path: str | Path) -> Path:
        """Return the shared basename of the six files inside ``path``."""
        return Path(path) / "index"

    def read(self, path: str | Path) -> Path:
        """Return the directory path without loading the index."""
        return Path(path)

    def validate(self, path: str | Path) -> None:
        """Check all six files and ask Bowtie 2 to inspect the index."""
        super().validate(path)
        directory = Path(path)
        if not directory.is_dir() or directory.is_symlink():
            raise ValueError(
                f"Invalid Bowtie 2 index directory {directory}: "
                "expected a real directory."
            )
        names = {entry.name for entry in directory.iterdir()}
        for suffix in ("bt2", "bt2l"):
            expected = {f"index.{part}.{suffix}" for part in _PARTS}
            if names != expected:
                continue
            if any(
                not (directory / name).is_file()
                or (directory / name).is_symlink()
                or (directory / name).stat().st_size == 0
                for name in expected
            ):
                break
            try:
                Bowtie2Inspect().run(
                    self.index_base(directory), summary=True, debug=False
                )
            except (Bowtie2ExecutionError, FileNotFoundError, OSError) as error:
                raise ValueError(
                    f"Invalid Bowtie 2 index directory {directory}: "
                    "bowtie2-inspect could not read the index."
                ) from error
            return
        raise ValueError(
            f"Invalid Bowtie 2 index directory {directory}: expected the six "
            "nonempty index.*.bt2 or index.*.bt2l files."
        )
