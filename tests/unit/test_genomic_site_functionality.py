#!/usr/bin/env python
"""
Filename: tests/unit/test_genomic_site_functionality.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Functional tests for GenomicSite.
License: LGPL-3.0-or-later
"""

import pytest
from Bio.Seq import Seq
from GenomeUtils.Genome import Locus

from ASOkai.Sites import GenomicSite


def test_genomic_site_builds_locus_and_derives_id(sample_sequence):
    site = GenomicSite(
        chr="12",
        start=100,
        end=115,
        strand="+",
        sequence=sample_sequence,
    )

    assert site.locus == Locus("12", 100, 115, "+")
    assert site.id == "site:12:100-115,+"
    assert site.sequence is sample_sequence


def test_genomic_site_requires_locus_to_match_sequence_length():
    with pytest.raises(
        ValueError,
        match="same length as the site sequence",
    ):
        GenomicSite(
            chr="12",
            start=100,
            end=115,
            strand="+",
            sequence=Seq("ACGT"),
        )


def test_genomic_site_repr_includes_all_defining_values(sample_sequence):
    site = GenomicSite(
        id="test_site",
        chr="12",
        start=100,
        end=115,
        strand="+",
        sequence=sample_sequence,
    )

    assert repr(site) == (
        "GenomicSite(id='test_site', "
        f"locus={site.locus!r}, sequence={sample_sequence!r})"
    )


def test_genomic_site_identity_uses_id_and_locus(sample_sequence):
    first = GenomicSite(
        id="site",
        chr="12",
        start=100,
        end=115,
        strand="+",
        sequence=sample_sequence,
    )
    same_identity = GenomicSite(
        id="site",
        chr="12",
        start=100,
        end=115,
        strand="+",
        sequence=sample_sequence,
    )
    different_id = GenomicSite(
        id="other",
        chr="12",
        start=100,
        end=115,
        strand="+",
        sequence=sample_sequence,
    )

    assert first == same_identity
    assert hash(first) == hash(same_identity)
    assert first != different_id
