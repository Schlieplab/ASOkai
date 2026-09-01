#!/usr/bin/env python
"""
Filename: src/ASOkai/Sites/_transcript_site.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Version: 0.1.1
Description: Defines sites located on one or more transcript sequences.
License: LGPL-3.0-or-later
"""

from Bio.Seq import Seq
from GenomeUtils.Genome import TranscriptLocus

from ._site import Site


class TranscriptSite(Site):
    """A sequence occurring at one or more transcript loci."""

    loci: list[TranscriptLocus]

    def __init__(
        self,
        loci: list[TranscriptLocus],
        sequence: Seq,
        id: str | None = None,
        **kwargs,
    ):
        """Initialize a transcript site.

        Args:
            loci: Locations of this sequence on spliced transcripts.
            sequence: Site sequence in the 5'-to-3' direction.
            id: Stable site identifier. When omitted, it is derived from the
                first transcript locus.
            kwargs: Additional serializable metadata attributes.
        """
        if not loci:
            raise ValueError("A transcript site requires at least one locus.")
        if len(loci) != len(set(loci)):
            raise ValueError("A transcript site cannot contain duplicate loci.")
        if any(len(locus) != len(sequence) for locus in loci):
            raise ValueError(
                "Every transcript locus must have the same length as the "
                "site sequence."
            )

        self.loci = sorted(loci)
        if id is None:
            first_locus = self.loci[0]
            id = (
                f"{first_locus.transcript_id}:"
                f"{first_locus.start}-{first_locus.end}"
            )

        Site.__init__(self, sequence=sequence, id=id, **kwargs)

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}(id={self.id!r}, "
            f"loci={self.loci!r})"
        )

    def __eq__(self, other: object) -> bool:
        """Compare transcript-site identity using the ID and sorted loci."""
        if not isinstance(other, TranscriptSite):
            return NotImplemented
        return self.id == other.id and self.loci == other.loci
