#!/usr/bin/env python
"""
Filename: src/ASOKai/sites/genomic_site.py
Author: Arash Ayat
Copyright: 2025, Alexander Schliep
Version: 0.1.0
Description: This file defines the GenomicSite class for representing genomic sites.
License: LGPL-3.0-or-later
"""
from GenomeUtils.Genome import Locus
from GenomeUtils.Genome import GenomeElement
from typing import TYPE_CHECKING, Literal, Dict, Any
from Bio.Seq import Seq
from .site import Site

if TYPE_CHECKING:
    from GenomeUtils.Genome import Genome

class GenomicSite(Site, GenomeElement):
    """Base class for genomic sites."""
    
    def __init__(self, 
                 chr: str, 
                 start: int, 
                 end: int, 
                 strand: Literal["+", "-"], 
                 sequence: Seq,
                 id: str = None,
                 genome: "Genome" = None,
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
        GenomeElement.__init__(self, id=id, locus=locus, genome=genome, **kwargs)
        
    def __repr__(self):
        return f"{self.__class__.__name__}(id='{self.id}', locus={self.locus!r}), sequence={self.sequence!r})"

    def _serialize_attribute(self, key: str, value: Any) -> Dict[str, Any]:
        if key == 'locus' and isinstance(value, Locus):
            return {
                'chr': value.chr,
                'start': value.start,
                'end': value.end,
                'strand': value.strand
            }
        return super()._serialize_attribute(key, value)
    