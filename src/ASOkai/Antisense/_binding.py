#!/usr/bin/env python
"""
Filename: src/ASOkai/Antisense/_binding.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Version: 0.1.1
Description: This file defines binding between an antisense therapeutic and a site.
License: LGPL-3.0-or-later
"""
from ..Utils import Serializable


class Binding(Serializable):
    """A binding between an antisense therapeutic and a site."""

    def __init__(self, therapeutic_id: str, site_id: str):
        self.therapeutic_id = therapeutic_id
        self.site_id = site_id
        super().__init__()
