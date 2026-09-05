#!/usr/bin/env python
"""
Filename: src/ASOkai/_pipeline/contracts/file_types/__init__.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: File-format contracts used by pipeline inputs and outputs.
License: LGPL-3.0-or-later
"""

from .csv import CsvFile, CsvRow, CsvTable
from .base import FileType
from .json import JsonFile
from .kff import KffFile


__all__ = [
    "CsvFile",
    "CsvRow",
    "CsvTable",
    "FileType",
    "JsonFile",
    "KffFile",
]
