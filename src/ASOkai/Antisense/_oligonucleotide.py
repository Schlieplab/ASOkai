#!/usr/bin/env python
"""
Filename: src/ASOkai/Antisense/_oligonucleotide.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: This file defines the Oligonucleotide class.
License: LGPL-3.0-or-later
"""

from Bio.Seq import Seq

from ..Biochemistry import Chemistry
from ..Utils import Serializable


class Oligonucleotide(Serializable):
    """A single oligonucleotide strand stored 5' to 3' using ``ACGT``."""

    _sequence: Seq
    chemistry: Chemistry | None
    _serialized_names = {"_sequence": "sequence"}

    def __init__(
        self,
        sequence: Seq,
        *,
        chemistry: Chemistry | None = None,
        **kwargs,
    ):
        """Initialize one oligonucleotide strand.

        Args:
            sequence: Nucleotide sequence stored in the 5' to 3' direction.
            chemistry: Optional chemistry attached to this strand.
            kwargs: Additional serializable metadata attributes.

        Raises:
            ValueError: If ``sequence`` is empty.
        """
        if not sequence:
            raise ValueError("Oligonucleotide sequence cannot be empty.")
        if chemistry is not None and not isinstance(chemistry, Chemistry):
            raise TypeError("Oligonucleotide chemistry must be Chemistry or None.")
        self._sequence = sequence
        self.chemistry = chemistry
        super().__init__(**kwargs)

    @property
    def sequence(self) -> Seq:
        """Return the strand sequence in the 5' to 3' direction."""
        return self._sequence
