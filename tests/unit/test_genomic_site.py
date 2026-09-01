#!/usr/bin/env python
"""
Filename: tests/unit/test_genomic_site.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Version: 0.1.1
Description: Unit tests for GenomicSite serialization/deserialization.
License: LGPL-3.0-or-later
"""

import pytest
from Bio.Seq import Seq
from GenomeUtils.Genome import Locus
from ASOkai.Sites import GenomicSite


@pytest.fixture
def sample_genomic_site(sample_sequence):
    """Create a sample GenomicSite for testing."""
    return GenomicSite(
        chr="12",
        start=100,
        end=115,
        strand="+",
        sequence=sample_sequence,
        id="test_site"
    )


@pytest.mark.unit
@pytest.mark.serialization
def test_genomic_site_serialized_shape(sample_genomic_site, sample_sequence):
    sample_genomic_site._genome = "excluded"
    sample_genomic_site._parent = "excluded"
    sample_genomic_site._children = []

    assert sample_genomic_site.to_dict() == {
        "__class__": "GenomicSite",
        "__module__": "ASOkai.Sites._genomic_site",
        "id": "test_site",
        "sequence": str(sample_sequence),
        "chr": "12",
        "start": 100,
        "end": 115,
        "strand": "+",
    }


@pytest.mark.unit
@pytest.mark.serialization
def test_genomic_site_reconstructs_flattened_fields(sample_sequence):
    site = GenomicSite.from_dict(
        {
            "__class__": "GenomicSite",
            "__module__": "ASOkai.Sites._genomic_site",
            "id": "test_site",
            "chr": "12",
            "start": 100,
            "end": 115,
            "strand": "+",
            "sequence": str(sample_sequence),
        }
    )

    assert isinstance(site, GenomicSite)
    assert isinstance(site.locus, Locus)
    assert site.id == "test_site"
    assert (site.chr, site.start, site.end, site.strand) == (
        "12",
        100,
        115,
        "+",
    )
    assert isinstance(site.sequence, Seq)
    assert site.sequence == sample_sequence


@pytest.mark.unit
@pytest.mark.serialization
def test_genomic_site_roundtrip_preserves_data(sample_genomic_site):
    reconstructed = GenomicSite.from_dict(sample_genomic_site.to_dict())

    assert reconstructed.id == sample_genomic_site.id
    assert reconstructed.locus == sample_genomic_site.locus
    assert reconstructed.sequence == sample_genomic_site.sequence
