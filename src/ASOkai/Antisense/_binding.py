#!/usr/bin/env python
"""
Filename: src/ASOkai/Antisense/_binding.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Version: 0.1.1
Description: This file defines binding between an oligonucleotide and a site.
License: LGPL-3.0-or-later
"""
from ..Utils import Serializable


class Binding(Serializable):
    """A physical binding relationship between one strand and one site.

    The relationship stores references by ID so that oligonucleotides and sites
    remain independently owned and are not duplicated during serialization.
    Design intent and binding-analysis results are modeled separately.
    """

    def __init__(self, oligonucleotide_id: str, site_id: str):
        self.oligonucleotide_id = oligonucleotide_id
        self.site_id = site_id
        super().__init__()
