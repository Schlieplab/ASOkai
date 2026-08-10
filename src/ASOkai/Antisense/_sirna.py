#!/usr/bin/env python
"""
Filename: src/ASOkai/Antisense/_sirna.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Version: 0.1.1
Description: This file defines the SiRNA class.
License: LGPL-3.0-or-later
"""

from ..Biochemistry import MechanismOfAction
from ._antisense_therapeutic import AntisenseTherapeutic
from ._oligonucleotide import Oligonucleotide


class SiRNA(AntisenseTherapeutic):
    """An antiparallel duplex whose two strands are each stored 5' to 3'."""

    _antisense_strand: Oligonucleotide
    _sense_strand: Oligonucleotide

    def __init__(
        self,
        id: str,
        antisense_strand: Oligonucleotide,
        sense_strand: Oligonucleotide,
        mechanism: MechanismOfAction,
        **kwargs,
    ):
        """Initialize a small interfering RNA duplex.

        Args:
            id: Unique therapeutic identifier.
            antisense_strand: Guide strand stored in the 5' to 3' direction.
            sense_strand: Passenger strand stored in the 5' to 3' direction.
            mechanism: Mechanism through which the siRNA acts.
            kwargs: Additional scalar values retained during serialization.
        """
        self._antisense_strand = antisense_strand
        self._sense_strand = sense_strand
        super().__init__(id=id, mechanism=mechanism, **kwargs)

    @property
    def antisense_strand(self) -> Oligonucleotide:
        """Return the antisense, or guide, strand in the 5' to 3' direction."""
        return self._antisense_strand

    @property
    def sense_strand(self) -> Oligonucleotide:
        """Return the sense, or passenger, strand in the 5' to 3' direction."""
        return self._sense_strand
