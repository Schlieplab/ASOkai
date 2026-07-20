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
    """A single oligonucleotide strand."""

    def __init__(self, id: str, sequence: Seq, chemistry: Chemistry, **kwargs):
        self.id = id
        self._sequence = sequence
        self.chemistry = chemistry
        super().__init__(**kwargs)

    @property
    def sequence(self) -> Seq:
        """Return the strand sequence."""
        return self._sequence
