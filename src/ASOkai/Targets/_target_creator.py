#!/usr/bin/env python
"""
Filename: src/ASOkai/Targets/target_creator.py
Author: Arash Ayat
Copyright: 2025, Alexander Schliep
Version: 0.1.0
Description: This file defines the base TargetCreator class.
License: LGPL-3.0-or-later
"""
from abc import ABC, abstractmethod
from ._target import Target
from GenomeUtils.Genome import Genome
from typing import Dict, Iterator, List, Optional
from ..Sites import Site

class TargetCreator(ABC):
    """Abstract base class for candidate target creators."""
    
    SITE_ID_PREFIX_PARTS: List[str] = ["ASOkai"]
    

    
    
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
    def site_id_generator(cls, start: int = 1, extra_prefix_parts: Optional[List[str]] = None) -> Iterator[str]:
        """
        Generates site IDs.

        Site ID format: SITE_ID_PREFIX_PARTS + extra_prefix_parts + incrementing number.
        Subclasses can extend SITE_ID_PREFIX_PARTS.

        Args:
            start (int, optional): The starting number for the enumerator. Defaults to 1.
            extra_prefix_parts (Optional[List[str]], optional): A list of additional strings
                to append to the prefix. Defaults to None.

        Yields:
            str: A site ID, e.g., 'ASOKAI-TS-KRAS-Exon2-0001'.
        """
        
        all_prefix_parts = cls.SITE_ID_PREFIX_PARTS[:] # Make a copy
        if extra_prefix_parts:
            all_prefix_parts.extend(extra_prefix_parts)

        prefix = "-".join(all_prefix_parts)
        i = start
        while True:
            yield f"{prefix}-S{i:05d}"
            i += 1 