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
from typing import Mapping, cast
from Bio.Seq import Seq
from ..Types import Strand
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
                 strand: Strand,
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
        """Return the target-gene sequence in the 5' to 3' direction."""
        return self._sequence

    def validate(self) -> None:
        """Validate a TargetGene before or after file serialization."""
        super().validate()
        if type(self.name) is not str or not self.name.strip():
            raise ValueError("Target gene name must be a non-blank string.")
        if type(self.chr) is not str or not self.chr.strip():
            raise ValueError("Target gene chromosome must be a non-blank string.")
        if type(self.start) is not int or self.start < 1:
            raise ValueError(
                "Target gene start must be an integer greater than zero."
            )
        if type(self.end) is not int or self.end < self.start:
            raise ValueError(
                "Target gene end must be an integer greater than or equal to start."
            )
        if type(self.strand) is not str or self.strand not in ("+", "-"):
            raise ValueError("Target gene strand must be '+' or '-'.")
        if not isinstance(self.sequence, Seq):
            raise TypeError("Target gene sequence must be a Bio.Seq.Seq.")
        if self._genome is not None and not isinstance(self._genome, Genome):
            raise TypeError("Target gene genome must be a Genome or None.")
        if self._parent is not None and not isinstance(self._parent, Chromosome):
            raise TypeError(
                "Target gene chromosome reference must be a Chromosome or None."
            )
        sequence = str(self.sequence)
        if not sequence or any(character.isspace() for character in sequence):
            raise ValueError(
                "Target gene sequence must be non-empty and contain no whitespace."
            )
