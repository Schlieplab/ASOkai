#!/usr/bin/env python
"""
Filename: src/ASOkai/Antisense/_sirna.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: This file defines the siRNA class.
License: LGPL-3.0-or-later
"""

from ..Biochemistry import MechanismOfAction
from ._antisense_therapeutic import AntisenseTherapeutic
from ._oligonucleotide import Oligonucleotide


class siRNA(AntisenseTherapeutic):
    """An antiparallel duplex whose two strands are each stored 5' to 3'."""

    _antisense_strand: Oligonucleotide
    _sense_strand: Oligonucleotide
    _serialized_names = {
        "_antisense_strand": "antisense_strand",
        "_sense_strand": "sense_strand",
    }

    def __init__(
        self,
        antisense_strand: Oligonucleotide,
        sense_strand: Oligonucleotide,
        mechanism: MechanismOfAction,
        *,
        id: str | None = None,
        **kwargs,
    ):
        """Initialize a small interfering RNA duplex.

        Args:
            id: Optional stored ID, checked against the design-derived ID.
            antisense_strand: Guide strand stored in the 5' to 3' direction.
            sense_strand: Passenger strand stored in the 5' to 3' direction.
            mechanism: Mechanism through which the siRNA acts.
            kwargs: Additional serializable metadata attributes.
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

    def _design_id(self) -> str:
        """Identify the mechanism, strands, and each strand's chemistry."""
        antisense_chemistry = (
            self._identity_suffix("c", self.antisense_strand.chemistry.id)
            if self.antisense_strand.chemistry else ""
        )
        sense_chemistry = (
            self._identity_suffix("c", self.sense_strand.chemistry.id)
            if self.sense_strand.chemistry else ""
        )
        return (
            f"sirna:m{self.mechanism.id}-"
            f"a{self._sequence_token(self.antisense_strand.sequence)}"
            f"{antisense_chemistry}-"
            f"p{self._sequence_token(self.sense_strand.sequence)}"
            f"{sense_chemistry}"
        )
