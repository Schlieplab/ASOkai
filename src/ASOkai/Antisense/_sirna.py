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
from ..Utils import Serializable
from ._antisense_therapeutic import AntisenseTherapeutic
from ._oligonucleotide import Oligonucleotide


class SiRNA(AntisenseTherapeutic, Serializable):
    """A duplex composed of antisense and sense oligonucleotide strands."""

    def __init__(
        self,
        id: str,
        antisense_strand: Oligonucleotide,
        sense_strand: Oligonucleotide,
        mechanism: MechanismOfAction,
        **kwargs,
    ):
        self.id = id
        self._antisense_strand = antisense_strand
        self._sense_strand = sense_strand
        AntisenseTherapeutic.__init__(self, mechanism=mechanism)
        Serializable.__init__(self, **kwargs)

    @property
    def antisense_strand(self) -> Oligonucleotide:
        """Return the antisense, or guide, strand."""
        return self._antisense_strand

    @property
    def sense_strand(self) -> Oligonucleotide:
        """Return the sense, or passenger, strand."""
        return self._sense_strand


SiRNA.register_attribute(
    "_antisense_strand",
    "antisense_strand",
    serialize=lambda strand: strand.to_dict(),
)
SiRNA.register_attribute(
    "_sense_strand",
    "sense_strand",
    serialize=lambda strand: strand.to_dict(),
)
