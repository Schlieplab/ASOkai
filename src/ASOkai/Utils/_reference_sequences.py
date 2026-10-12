#!/usr/bin/env python
"""
Filename: src/ASOkai/Utils/_reference_sequences.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Named sequences and temporary reference FASTA writing.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from Bio.Seq import Seq
from Bio.SeqIO import write
from Bio.SeqRecord import SeqRecord


@dataclass(frozen=True)
class ReferenceSequence:
    """A named sequence to include in a sequence-search index."""

    id: str
    sequence: Seq

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id or any(
            character.isspace() or character == ">" for character in self.id
        ):
            raise ValueError("Reference sequence ID must be nonempty and FASTA-safe.")
        if not isinstance(self.sequence, Seq) or len(self.sequence) == 0:
            raise ValueError("Reference sequence must be a nonempty Bio.Seq.Seq.")


def write_reference_fasta(
    references: Sequence[ReferenceSequence], path: str | Path
) -> Path:
    """Write named sequences as a FASTA for an external index builder."""
    if not references:
        raise ValueError("At least one reference sequence is required.")
    names = [reference.id for reference in references]
    if len(names) != len(set(names)):
        raise ValueError("Reference sequence IDs must be unique.")
    destination = Path(path)
    records = (
        SeqRecord(reference.sequence, id=reference.id, description="")
        for reference in references
    )
    write(records, destination, "fasta")
    return destination
