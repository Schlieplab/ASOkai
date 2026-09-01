#!/usr/bin/env python
"""
Filename: src/ASOkai/Sites/_genomic_site.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Version: 0.1.1
Description: This file defines the GenomicSite class for representing genomic sites.
License: LGPL-3.0-or-later
"""

from Bio.Seq import Seq
from GenomeUtils.Genome import Genome, GenomeElement, Locus

from ..Types import Strand
from ._site import Site


class GenomicSite(Site, GenomeElement):
    """A sequence located at one genomic locus."""

    locus: Locus

    _flattened_attributes = frozenset({"locus"})
    _non_serializable_attrs = {"_genome", "_parent", "_children"}

    def __init__(
        self,
        chr: str,
        start: int,
        end: int,
        strand: Strand,
        sequence: Seq,
        id: str | None = None,
        genome: Genome | None = None,
        **kwargs,
    ):
        """Initialize a genomic site.

        Args:
            chr: Chromosome containing the site.
            start: The start position of the site (1-based inclusive).
            end: The end position of the site (1-based inclusive).
            strand: Genomic strand containing the site.
            sequence: Site sequence in the 5'-to-3' direction.
            id: Stable site identifier. Constructors derive it from the locus
                when omitted.
            genome: Optional genome containing the site.
            kwargs: Additional serializable metadata attributes.

        Raises:
            ValueError: If the sequence and locus lengths differ.
        """
        locus = Locus(chr, start, end, strand)
        if len(sequence) != len(locus):
            raise ValueError(
                "The genomic locus must have the same length as the site "
                "sequence."
            )

        if id is None:
            id = str(locus)

        Site.__init__(self, id=id, sequence=sequence, **kwargs)
        GenomeElement.__init__(self, id=id, locus=locus, genome=genome)

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}(id={self.id!r}, "
            f"locus={self.locus!r}, sequence={self.sequence!r})"
        )
