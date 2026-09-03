#!/usr/bin/env python
"""
Filename: src/ASOkai/Sites/_site.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: This file defines the base Site class.
License: LGPL-3.0-or-later
"""
from abc import ABC, abstractmethod

from Bio.Seq import Seq

from ..Utils import Serializable


class Site(Serializable, ABC):
    """Abstract base class for sites whose sequences are stored 5' to 3'."""

    id: str
    _sequence: Seq
    _serialized_names = {"_sequence": "sequence"}

    def __init__(self, id: str, sequence: Seq, **kwargs):
        """Initialize a site.

        Args:
            id: Stable site identifier.
            sequence: Site sequence in the 5'-to-3' direction.
            kwargs: Additional serializable metadata attributes.
        """
        self.id = id
        self._sequence = sequence

        Serializable.__init__(self, **kwargs)

    @property
    def sequence(self) -> Seq:
        """Return the site sequence in the 5' to 3' direction."""
        return self._sequence

    @abstractmethod
    def __repr__(self) -> str:
        """Return a string representation of this site."""
        raise NotImplementedError
