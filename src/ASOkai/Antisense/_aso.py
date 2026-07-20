#!/usr/bin/env python
"""
Filename: src/ASOkai/Antisense/_aso.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Version: 0.1.1
Description: This file defines the ASO class, representing an antisense oligonucleotide.
License: LGPL-3.0-or-later
"""
from Bio.Seq import Seq

from ..Biochemistry import Chemistry, MechanismOfAction
from ._antisense_therapeutic import AntisenseTherapeutic
from ._oligonucleotide import Oligonucleotide


class ASO(Oligonucleotide, AntisenseTherapeutic):
    """A single-stranded antisense oligonucleotide therapeutic."""

    def __init__(
        self,
        id: str,
        sequence: Seq,
        chemistry: Chemistry,
        mechanism: MechanismOfAction,
        **kwargs,
    ):
        Oligonucleotide.__init__(
            self,
            id=id,
            sequence=sequence,
            chemistry=chemistry,
            **kwargs,
        )
        AntisenseTherapeutic.__init__(self, mechanism=mechanism)

    @property
    def antisense_strand(self) -> Oligonucleotide:
        """Return this ASO, which is itself the antisense strand."""
        return self
