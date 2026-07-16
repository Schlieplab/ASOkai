#!/usr/bin/env python
"""
Filename: src/ASOkai/Sites/_site.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Version: 0.1.1
Description: This file defines the base Site class.
License: LGPL-3.0-or-later
"""
from abc import ABC, abstractmethod
from Bio.Seq import Seq
from typing import Dict
from ..Utils import Serializable


class Site(Serializable, ABC):
    """Abstract base class for sites that may or may not be genomic."""

    def __init__(self,
                 id: str,
                 sequence: Seq,
                 **kwargs):
        """
        Initializes a Site object.

        Args:
            id: The ID of the site.
            sequence: The sequence of the site.
            kwargs: Additional keyword arguments.
        """
        self.id = id
        self._sequence = sequence
        
        Serializable.__init__(self, **kwargs)

    @property
    def sequence(self) -> Seq:
        return self._sequence

    @abstractmethod
    def __repr__(self) -> str:
        """Return a string representation of this site."""
        raise NotImplementedError

    
