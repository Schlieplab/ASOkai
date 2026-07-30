#!/usr/bin/env python
"""
Filename: src/ASOkai/Antisense/_oligonucleotide.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Version: 0.1.1
Description: This file defines the Oligonucleotide class.
License: LGPL-3.0-or-later
"""
from Bio.Seq import Seq

from ..Biochemistry import Chemistry
from ..Utils import Serializable


class Oligonucleotide(Serializable):
    """A single oligonucleotide strand stored 5' to 3' using ``ACGT``."""

    _sequence: Seq
    _chemistry: Chemistry

    def __init__(self, sequence: Seq, chemistry: Chemistry, **kwargs):
        self._sequence = sequence
        self._chemistry = chemistry
        super().__init__(**kwargs)

    @property
    def sequence(self) -> Seq:
        """Return the strand sequence in the 5' to 3' direction."""
        return self._sequence

    @property
    def chemistry(self) -> Chemistry:
        return self._chemistry
