#!/usr/bin/env python
"""
Filename: src/ASOkai/Antisense/_antisense_therapeutic.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Version: 0.1.1
Description: This file defines the base AntisenseTherapeutic class.
License: LGPL-3.0-or-later
"""
from abc import ABC, abstractmethod

from Bio.Seq import Seq

from ..Biochemistry import MechanismOfAction
from ..Utils import Serializable
from ._oligonucleotide import Oligonucleotide


class AntisenseTherapeutic(Serializable, ABC):
    """Base class for therapeutics that act through an antisense strand.

    ``sequence`` means the antisense-strand sequence in the 5' to 3'
    direction. For a multi-stranded therapeutic, it does not include the sense
    or passenger strand.
    """

    id: str
    mechanism: MechanismOfAction

    def __init__(self, id: str, mechanism: MechanismOfAction, **kwargs):
        self.id = id
        self.mechanism = mechanism
        super().__init__(**kwargs)

    @property
    @abstractmethod
    def antisense_strand(self) -> Oligonucleotide:
        """Return the oligonucleotide strand responsible for target binding."""
        raise NotImplementedError

    @property
    def sequence(self) -> Seq:
        """Return the antisense-strand sequence in the 5' to 3' direction."""
        return self.antisense_strand.sequence
