#!/usr/bin/env python
"""
Filename: src/ASOkai/Biochemistry/_chemistry.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: This file defines the base Chemistry class.
License: LGPL-3.0-or-later
"""

from abc import ABC

from ..Utils import Serializable


class Chemistry(Serializable, ABC):
    """Base class for future nucleotide-level chemistry models.

    Chemistry is intentionally not attached to oligonucleotides yet. Its
    representation will be defined when per-nucleotide modifications are
    implemented.
    """
