#!/usr/bin/env python
"""
Filename: tests/unit/test_reference_sequences.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Tests for named reference sequence FASTA conversion.
License: LGPL-3.0-or-later
"""

from pathlib import Path

from Bio.Seq import Seq
import pytest

from ASOkai.Utils import ReferenceSequence, write_reference_fasta


def test_writes_multiple_named_sequences(tmp_path: Path):
    references = [
        ReferenceSequence("gene:1", Seq("ACGT")),
        ReferenceSequence("transcript-2", Seq("TTAA")),
    ]
    output = tmp_path / "references.fa"

    assert write_reference_fasta(references, output) == output
    assert output.read_text(encoding="utf-8") == (
        ">gene:1\nACGT\n>transcript-2\nTTAA\n"
    )


def test_rejects_unnamed_or_duplicate_references(tmp_path: Path):
    with pytest.raises(ValueError, match="FASTA-safe"):
        ReferenceSequence("gene one", Seq("ACGT"))
    with pytest.raises(ValueError, match="unique"):
        write_reference_fasta(
            [ReferenceSequence("gene", Seq("ACGT")),
             ReferenceSequence("gene", Seq("TTAA"))],
            tmp_path / "references.fa",
        )
    assert not (tmp_path / "references.fa").exists()
