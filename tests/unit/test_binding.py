#!/usr/bin/env python
"""Tests for oligonucleotide-to-site binding relationships."""

from ASOkai.Antisense import Binding


def test_binding_references_one_oligonucleotide_and_site():
    binding = Binding(oligonucleotide_id="oligo-1", site_id="site-1")

    assert binding.oligonucleotide_id == "oligo-1"
    assert binding.site_id == "site-1"


def test_binding_serialization_roundtrip():
    binding = Binding(oligonucleotide_id="oligo-1", site_id="site-1")

    data = binding.to_dict()
    reconstructed = Binding.from_dict(data)

    assert data == {
        "__class__": "Binding",
        "__module__": "ASOkai.Antisense._binding",
        "oligonucleotide_id": "oligo-1",
        "site_id": "site-1",
    }
    assert isinstance(reconstructed, Binding)
    assert reconstructed.oligonucleotide_id == binding.oligonucleotide_id
    assert reconstructed.site_id == binding.site_id
