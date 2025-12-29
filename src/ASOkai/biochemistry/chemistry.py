#!/usr/bin/env python
"""
Filename: src/ASOKai/biochemistry/chemistry.py
Author: Arash Ayat
Copyright: 2025, Alexander Schliep
Version: 0.1.0
Description: This file defines the base Chemistry class.
License: LGPL-3.0-or-later
"""
from abc import ABC, abstractmethod


class Chemistry(ABC):
    """Abstract base class for antisense construct chemistry."""

    @property
    @abstractmethod
    def Smiles(self) -> str:
        """Return the chemistry SMILES"""
        pass


