#!/usr/bin/env python
"""
Filename: src/ASOKai/targets/target_gene.py
Author: Arash Ayat
Copyright: 2025, Alexander Schliep
Version: 0.1.0
Description: This file defines the TargetGene class for representing target genes.
License: LGPL-3.0-or-later
"""
from GenomeUtils.Genome import Gene, Genome, Chromosome, Locus
from .target import Target
from typing import Literal, Any
from Bio.Seq import Seq
from typing import Dict
from ..sites import Site

class TargetGene(Target, Gene):
    """
    Represents a candidate target gene, inheriting from GenomeUtils.Gene.
    """
    def __init__(self, 
                 id: str,
                 name: str,
                 chr: str,
                 start: int,
                 end: int,
                 strand: Literal["+", "-"],
                 sequence: Seq,
                 target_sites: Dict[str, Site],
                 genome: Genome = None,
                 chromosome: "Chromosome" = None, 
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
            sequence: The sequence of the candidate target gene.
            target_sites: The target sites of the candidate target gene.
            genome: The genome of the candidate target gene, Optional.
            chromosome: The chromosome of the candidate target gene, Optional.
            **kwargs: Additional keyword arguments.
        """
        self._sequence = sequence
        
        Target.__init__(self, id, 
                        target_sites, **kwargs)
        
        Gene.__init__(self, id, name, 
                      chr, start, end, 
                      strand, 
                      genome = genome, 
                      chromosome = chromosome)
        

    @property
    def sequence(self) -> Seq:
        return self._sequence
    
    def _serialize_attribute(self, key: str, value: Any) -> Dict[str, Any]:
        if key == 'locus' and isinstance(value, Locus):
            return {
                'chr': value.chr,
                'start': value.start,
                'end': value.end,
                'strand': value.strand
            }
        return super()._serialize_attribute(key, value)
    
    def _serialize_value(self, value: Any) -> Any:
        if isinstance(value, Seq):
            return {
                '__type__': 'Bio.Seq.Seq',
                'sequence': str(value)
            }
        return super()._serialize_value(value)

    @classmethod
    def _deserialize_value(cls, value_data: Any) -> Any:
        if isinstance(value_data, dict) and value_data.get('__type__') == 'Bio.Seq.Seq':
            return Seq(value_data['sequence'])
        return super()._deserialize_value(value_data)

    @classmethod
    def _get_init_arg_name_map(cls) -> Dict[str, str]:
        # Get the map from the parent class and add our own
        name_map = super()._get_init_arg_name_map()
        name_map.update({"_sequence": "sequence"
                         ,"_target_sites": "target_sites"})
        return name_map

