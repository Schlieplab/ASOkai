from turtle import back
from genome_utils import Site
from genome_utils import GenomeElement
from genome_utils import Genome
from typing import TYPE_CHECKING, Literal
from Bio.Seq import Seq
from abc import ABC, abstractmethod

if TYPE_CHECKING:
    from genome_utils import GenomeElement
    from genome_utils import Genome
    
class TargetSite(Site, ABC):
    """Abstract base class for target sites."""
    def __init__(self, 
                 id: str,
                 chr: str, 
                 start: int, 
                 end: int, 
                 strand: Literal["+", "-"], 
                 sequence: Seq,
                 parent: "GenomeElement" = None,
                 genome: "Genome" = None,
                 **kwargs):
        """
        Initializes a TargetSite object.
        
        Args:
            id: The ID of the target site.
            chr: The chromosome of the target site.
            start: The start position of the target site.
            end: The end position of the target site.
            strand: The strand of the target site.
            sequence: The sequence of the target site.
            parent: The parent of the target site.
            genome: The genome of the target site.
            kwargs: Additional keyword arguments.
        """
        super().__init__(chr, 
                         start, 
                         end, 
                         strand, 
                         sequence, 
                         id = id, 
                         parent = parent, 
                         genome = genome, 
                         **kwargs)
    
    @abstractmethod
    def accessibility_score(self) -> float:
        """Return the accessibility score of the target site (Between 0 and 1)."""
        pass
    
