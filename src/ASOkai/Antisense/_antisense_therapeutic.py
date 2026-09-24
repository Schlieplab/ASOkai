#!/usr/bin/env python
"""
Filename: src/ASOkai/Antisense/_antisense_therapeutic.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
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
    or passenger strand. Subclasses define the design-derived ID; a supplied
    stored ID must match it.
    """

    id: str
    mechanism: MechanismOfAction

    def __init__(
        self,
        mechanism: MechanismOfAction,
        *,
        id: str | None = None,
        **kwargs,
    ):
        self.mechanism = mechanism
        design_id = self._design_id()
        if id is not None and id != design_id:
            raise ValueError(
                f"Therapeutic ID {id!r} does not match design ID "
                f"{design_id!r}."
            )
        self.id = design_id
        super().__init__(**kwargs)

    @abstractmethod
    def _design_id(self) -> str:
        """Return the identifier defined by this therapeutic's design."""
        raise NotImplementedError

    @staticmethod
    def _sequence_token(sequence: Seq) -> str:
        """Encode ACGT with two bits per base, retaining its length."""
        letters = str(sequence)
        if not letters:
            raise ValueError("A design sequence cannot be empty.")
        if all(base in "ACGT" for base in letters):
            value = 0
            for base in letters:
                value = (value << 2) | "ACGT".index(base)
            return f"s{len(letters)}x{value:0{(len(letters) + 1) // 2}x}"
        # Preserve ambiguous and lower-case bases that two bits cannot encode.
        return f"s{len(letters)}u{letters.encode('utf-8').hex()}"

    @staticmethod
    def _identity_suffix(label: str, identifier: str) -> str:
        """Length-prefix an optional ID so adjacent fields cannot collide."""
        return f"-{label}{len(identifier)}:{identifier}"

    @property
    @abstractmethod
    def antisense_strand(self) -> Oligonucleotide:
        """Return the oligonucleotide strand responsible for target binding."""
        raise NotImplementedError

    @property
    def sequence(self) -> Seq:
        """Return the antisense-strand sequence in the 5' to 3' direction."""
        return self.antisense_strand.sequence
