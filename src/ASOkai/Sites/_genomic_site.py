#!/usr/bin/env python
"""
Filename: src/ASOkai/Sites/_genomic_site.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Version: 0.1.1
Description: This file defines the GenomicSite class for representing genomic sites.
License: LGPL-3.0-or-later
"""
from GenomeUtils.Genome import Locus
from GenomeUtils.Genome import GenomeElement
from typing import TYPE_CHECKING, Literal, cast
from Bio.Seq import Seq
from ._site import Site

if TYPE_CHECKING:
    from GenomeUtils.Genome import Genome


class GenomicSite(Site, GenomeElement):
    """Base class for genomic sites."""
    
    # Attributes to exclude from serialization (references to large/circular objects)
    _non_serializable_attrs = {'_genome', '_parent', '_children'}
    
    def __init__(self, 
                 chr: str, 
                 start: int, 
                 end: int, 
                 strand: Literal["+", "-"], 
                 sequence: Seq,
                 id: str | None = None,
                 genome: "Genome | None" = None,
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
    
