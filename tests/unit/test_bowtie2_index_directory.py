#!/usr/bin/env python
"""
Filename: tests/unit/test_bowtie2_index_directory.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Tests for the Bowtie 2 index directory contract.
License: LGPL-3.0-or-later
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from ASOkai._pipeline.contracts.file_types import Bowtie2IndexDirectory


@pytest.mark.parametrize("suffix", ["bt2", "bt2l"])
def test_valid_six_file_index(monkeypatch, tmp_path: Path, suffix: str):
    from ASOkai._pipeline.contracts.file_types import bowtie2

    inspector = MagicMock()
    monkeypatch.setattr(bowtie2, "Bowtie2Inspect", lambda: inspector)
    for part in ("1", "2", "3", "4", "rev.1", "rev.2"):
        (tmp_path / f"index.{part}.{suffix}").write_bytes(b"index")

    Bowtie2IndexDirectory().validate(tmp_path)

    inspector.run.assert_called_once_with(
        tmp_path / "index", summary=True, debug=False
    )


@pytest.mark.parametrize("change", ["missing", "empty", "extra", "mixed"])
def test_rejects_incomplete_or_mixed_index(tmp_path: Path, change: str):
    parts = ("1", "2", "3", "4", "rev.1", "rev.2")
    for part in parts:
        suffix = "bt2l" if change == "mixed" and part == "rev.2" else "bt2"
        content = b"" if change == "empty" and part == "1" else b"index"
        (tmp_path / f"index.{part}.{suffix}").write_bytes(content)
    if change == "missing":
        (tmp_path / "index.rev.2.bt2").unlink()
    if change == "extra":
        (tmp_path / "stray.txt").write_text("stray")

    with pytest.raises(ValueError, match="six nonempty"):
        Bowtie2IndexDirectory().validate(tmp_path)


def test_rejects_index_that_inspector_cannot_read(monkeypatch, tmp_path: Path):
    from ASOkai._pipeline.contracts.file_types import bowtie2

    inspector = MagicMock()
    inspector.run.side_effect = FileNotFoundError("bowtie2-inspect")
    monkeypatch.setattr(bowtie2, "Bowtie2Inspect", lambda: inspector)
    for part in ("1", "2", "3", "4", "rev.1", "rev.2"):
        (tmp_path / f"index.{part}.bt2").write_bytes(b"index")

    with pytest.raises(ValueError, match="could not read"):
        Bowtie2IndexDirectory().validate(tmp_path)
