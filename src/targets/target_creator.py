from abc import ABC, abstractmethod
from targets.target import Target
from GenomeUtils.Genome import Genome
from typing import Dict
from Sites import Site

class TargetCreator(ABC):
    """Abstract base class for candidate target creators."""
    
    @abstractmethod
    @staticmethod
    def _extract_target_sites() -> Dict[str, Site]:
        """
        Abstract method to extract target sites.
        """
        pass

    
    
    @abstractmethod
    @classmethod
    def from_file(cls, file_path: str) -> Target:
        """
        Abstract method to load candidate from file.
        
        """
        pass
    
    @abstractmethod
    @classmethod
    def from_genome(cls, genome: Genome, target_id: str) -> Target:
        """
        Abstract method to load candidate from genome.
        """
        pass