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

    therapeutic_id: str
    site_id: str

    def __init__(self, therapeutic_id: str, site_id: str):
        """Initialize a therapeutic-to-site relationship.

        Args:
            therapeutic_id: ID of a therapeutic in the paired output.
            site_id: ID of a site in the input target gene.
        """
        self.therapeutic_id = therapeutic_id
        self.site_id = site_id
        super().__init__()
