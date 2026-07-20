#!/usr/bin/env python
"""
Filename: src/ASOkai/Biochemistry/_chemistry.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Version: 0.1.1
Description: This file defines the base Chemistry class.
License: LGPL-3.0-or-later
"""
from abc import ABC, abstractmethod

from ..Utils import Serializable


class Chemistry(Serializable, ABC):
    """Abstract base class for oligonucleotide chemistry."""

    @property
    @abstractmethod
    def Smiles(self) -> str:
        """Return the chemistry SMILES"""
        pass

