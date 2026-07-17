#!/usr/bin/env python
"""
Filename: src/ASOkai/Targets/_target_gene.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Version: 0.1.1
Description: This file defines the TargetGene class for representing target genes.
License: LGPL-3.0-or-later
"""
from GenomeUtils.Genome import Gene, Genome, Chromosome
from ._target import Target
from typing import Literal, Mapping, cast
from Bio.Seq import Seq
from ..Sites import Site


class TargetGene(Target, Gene):
    """
    Represents a candidate target gene, inheriting from GenomeUtils.Gene.
    """
    
    # Attributes to exclude from serialization (references to large/circular objects)
    _non_serializable_attrs = {'_genome', '_parent', '_children'}
    
    def __init__(self, 
                 id: str,
                 name: str,
                 chr: str,
                 start: int,
                 end: int,
                 strand: Literal["+", "-"],
                 sequence: Seq,
                 sites: Mapping[str, Site],
                 genome: Genome | None = None,
                 chromosome: "Chromosome | None" = None,
                 **kwargs):
        """
        Initializes a `TargetGene` object.
        
        Args:
            id: The ID of the candidate target gene.
            name: The name of the candidate target gene.
            chr: The chromosome of the candidate target gene.
            start: The start position of the candidate target gene.
            end: The end position of the candidate target gene.
            strand: The strand of the candidate target gene.
            sequence: The pre-mRNA sequence of the candidate target gene.
            sites: The target sites of the candidate target gene.
            genome: The genome of the candidate target gene, Optional.
            chromosome: The chromosome of the candidate target gene, Optional.
            **kwargs: Additional keyword arguments.
        """
        self._sequence = sequence
        
        Target.__init__(self, id, 
                        sites, **kwargs)
        
        Gene.__init__(self, id, name, 
                      chr, start, end, 
                      strand, 
                      genome=cast(Genome, genome),
                      chromosome=cast(Chromosome, chromosome))

    @property
    def sequence(self) -> Seq:
        return self._sequence

