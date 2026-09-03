#!/usr/bin/env python
"""
Filename: tests/unit/test_binding.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Tests for therapeutic-to-site binding relationships.
License: LGPL-3.0-or-later
"""

from ASOkai.Antisense import Binding


def test_binding_references_and_serializes_one_therapeutic_and_site():
    binding = Binding(therapeutic_id="aso-1", site_id="site-1")

    data = binding.to_dict()
    reconstructed = Binding.from_dict(data)

    assert data == {
        "__class__": "Binding",
        "__module__": "ASOkai.Antisense._binding",
        "therapeutic_id": "aso-1",
        "site_id": "site-1",
    }
    assert isinstance(reconstructed, Binding)
    assert reconstructed.therapeutic_id == binding.therapeutic_id
    assert reconstructed.site_id == binding.site_id
