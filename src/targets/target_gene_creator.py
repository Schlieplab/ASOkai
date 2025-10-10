from .target_creator import TargetCreator
from .target_gene import TargetGene
from GenomeUtils.Genome import Genome, Gene
from typing import Literal, Dict
from Bio.Seq import Seq
from Sites import Site

class TargetGeneCreator(TargetCreator):
    """
    Creator for TargetGene objects using factory methods.
    This class is not meant to be instantiated.
    """

    @staticmethod
    def _extract_target_sites(gene: Gene, 
                              region: str = "exonic_only", 
                              id_prefix: str = "TS") -> Dict[str, Site]:
        """
        Extracts genomic sites from a Gene object's exons.
        """
        pass

    @classmethod
    def from_genome(cls, genome: Genome, target_id: str) -> TargetGene:
        """
        Creates a TargetGene object from a gene ID within a Genome object.
        """
        pass
    
    @classmethod
    def from_file(cls, file_path: str):
        """
        Load a TargetGene object from a file.
        """
        pass
    