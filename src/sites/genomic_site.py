from GenomeUtils.Genome import Locus
from GenomeUtils.Genome import GenomeElement
from typing import TYPE_CHECKING, Literal
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
            
        Site.__init__(sequence, id=id, **kwargs)
        GenomeElement.__init__(id, locus, genome = genome, **kwargs)
        
    def __repr__(self):
        return f"{self.__class__.__name__}(id='{self.id}', locus={self.locus!r}')"
    