from abc import ABC, abstractmethod
from .target import Target
from GenomeUtils.Genome import Genome
from typing import Dict, Iterator, List, Optional
from ..sites import Site

class TargetCreator(ABC):
    """Abstract base class for candidate target creators."""
    
    TARGET_ID_PREFIX_PARTS: List[str] = ["ASOKAI", "TS"]
    

    
    
    @classmethod
    @abstractmethod
    def from_file(cls, file_path: str) -> Target:
        """
        Abstract method to load candidate from file.
        
        """
        pass
    
    
    @classmethod
    @abstractmethod
    def from_genome(cls, genome: Genome, target_id: str) -> Target:
        """
        Abstract method to load candidate from genome.
        """
        pass

    @classmethod
    def target_id_generator(cls, start: int = 1, extra_prefix_parts: Optional[List[str]] = None) -> Iterator[str]:
        """
        Generates target IDs.

        The ID is constructed from TARGET_ID_PREFIX_PARTS class variable,
        any provided extra_prefix_parts, and an incrementing number.
        Subclasses can extend TARGET_ID_PREFIX_PARTS to add their own identifiers.

        Args:
            start (int, optional): The starting number for the enumerator. Defaults to 1.
            extra_prefix_parts (Optional[List[str]], optional): A list of additional strings
                to append to the prefix. Defaults to None.

        Yields:
            str: A target ID, e.g., 'ASOKAI-TS-KRAS-Exon2-0001'.
        """
        
        all_prefix_parts = cls.TARGET_ID_PREFIX_PARTS[:] # Make a copy
        if extra_prefix_parts:
            all_prefix_parts.extend(extra_prefix_parts)

        prefix = "-".join(all_prefix_parts)
        i = start
        while True:
            yield f"{prefix}-{i:04d}"
            i += 1 