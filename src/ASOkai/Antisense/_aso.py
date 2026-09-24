#!/usr/bin/env python
"""
Filename: src/ASOkai/Antisense/_aso.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: This file defines the ASO class, representing an antisense oligonucleotide.
License: LGPL-3.0-or-later
"""
from Bio.Seq import Seq

from ..Biochemistry import Chemistry, MechanismOfAction
from ._antisense_therapeutic import AntisenseTherapeutic
from ._oligonucleotide import Oligonucleotide


class ASO(Oligonucleotide, AntisenseTherapeutic):
    """A single-stranded antisense therapeutic stored 5' to 3'."""

    def __init__(
        self,
        sequence: Seq,
        mechanism: MechanismOfAction,
        *,
        chemistry: Chemistry | None = None,
        id: str | None = None,
        **kwargs,
    ):
        """Initialize an ASO.

        Args:
            id: Optional stored ID, checked against the design-derived ID.
            sequence: Antisense-strand sequence in the 5' to 3' direction.
            mechanism: Mechanism through which the ASO acts.
            chemistry: Optional chemistry of this strand.
            kwargs: Additional serializable metadata attributes.
        """
        super().__init__(
            id=id,
            sequence=sequence,
            mechanism=mechanism,
            chemistry=chemistry,
            **kwargs,
        )

    @property
    def antisense_strand(self) -> Oligonucleotide:
        """Return this ASO, which is itself the antisense strand."""
        return self

    def _design_id(self) -> str:
        """Identify the mechanism, strand sequence, and optional chemistry."""
        chemistry = (
            self._identity_suffix("c", self.chemistry.id)
            if self.chemistry else ""
        )
        return (
            f"aso:m{self.mechanism.id}-"
            f"{self._sequence_token(self.sequence)}{chemistry}"
        )
