#!/usr/bin/env python
"""
Filename: src/ASOkai/Sites/_genomic_site.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Version: 0.1.1
Description: This file defines the GenomicSite class for representing genomic sites.
License: LGPL-3.0-or-later
"""
from GenomeUtils.Genome import Genome, GenomeElement, Locus
from typing import cast
from Bio.Seq import Seq
from ..Types import Strand
from ._site import Site


class GenomicSite(Site, GenomeElement):
    """Base class for genomic sites."""
    
    # Attributes to exclude from serialization (references to large/circular objects)
    _non_serializable_attrs = {'_genome', '_parent', '_children'}
    
    def __init__(self, 
                 chr: str, 
                 start: int, 
                 end: int, 
                 strand: Strand,
                 sequence: Seq,
                 id: str | None = None,
                 genome: Genome | None = None,
                 **kwargs):
        """
        Initializes a GenomicSite object.
        
        Args:
            chr: The chromosome of the site.
            start: The start position of the site (1-based inclusive).
            end: The end position of the site (1-based inclusive).
            strand: The strand of the site.
            sequence: The sequence of the site.
            id: The ID of the site. Optional, defaults to None.
            genome: The genome of the site. Optional, defaults to None.
            kwargs: Additional keyword arguments.
        """
        locus = Locus(chr, start, end, strand)
        
        if id is None:
            id = str(locus)
            
        Site.__init__(self, id=id, sequence=sequence, **kwargs)
        GenomeElement.__init__(self, id=id, locus=locus, genome=cast("Genome", genome))
        
    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(id='{self.id}', locus={self.locus!r}), sequence={self.sequence!r})"

    def validate(self) -> None:
        """Validate a serialized genomic site."""
        super().validate()
        if type(self.chr) is not str or not self.chr.strip():
            raise ValueError("Genomic site chromosome must be a non-blank string.")
        if type(self.start) is not int or self.start < 1:
            raise ValueError("Genomic site start must be an integer greater than zero.")
        if type(self.end) is not int or self.end < self.start:
            raise ValueError(
                "Genomic site end must be an integer greater than or equal to start."
            )
        if type(self.strand) is not str or self.strand not in ("+", "-"):
            raise ValueError("Genomic site strand must be '+' or '-'.")
        if self._genome is not None and not isinstance(self._genome, Genome):
            raise TypeError("Genomic site genome must be a Genome or None.")
        if len(self.sequence) != self.end - self.start + 1:
            raise ValueError(
                "Genomic site sequence length must match its inclusive interval."
            )
    
