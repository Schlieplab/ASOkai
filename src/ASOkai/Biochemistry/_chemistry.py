#!/usr/bin/env python
"""
Filename: src/ASOkai/Biochemistry/_chemistry.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: This file defines the base Chemistry class.
License: LGPL-3.0-or-later
"""

from ..Utils import Serializable


class Chemistry(Serializable):
    """Optional oligonucleotide chemistry with a stable design identity.

    The representation of individual nucleotide modifications is deferred.
    """

    id: str

    def __init__(self, id: str, **kwargs):
        """Attach a stable chemistry ID without defining its modifications."""
        if not isinstance(id, str) or not id:
            raise ValueError("Chemistry ID must be a non-empty string.")
        self.id = id
        super().__init__(**kwargs)
