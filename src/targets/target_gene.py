from GenomeUtils.Genome import Gene, Genome, Chromosome
from .target import Target
from typing import Literal
from Bio.Seq import Seq
from typing import Dict
from Sites import Site

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

