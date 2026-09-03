#!/usr/bin/env python
"""
Filename: tests/unit/test_transcript_site_functionality.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Functional tests for TranscriptSite.
License: LGPL-3.0-or-later
"""

import pytest
from Bio.Seq import Seq
from GenomeUtils.Genome import TranscriptLocus

from ASOkai.Sites import TranscriptSite


@pytest.mark.unit
def test_transcript_site_sorts_and_copies_loci_and_derives_id():
    loci = [
        TranscriptLocus("ENST00000002", 30, 34),
        TranscriptLocus("ENST00000001", 10, 14),
    ]

    site = TranscriptSite(loci=loci, sequence=Seq("ACGT"))
    loci.append(TranscriptLocus("ENST00000003", 40, 44))

    assert site.id == "ENST00000001:10-14"
    assert site.loci == [
        TranscriptLocus("ENST00000001", 10, 14),
        TranscriptLocus("ENST00000002", 30, 34),
    ]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("loci", "message"),
    [
        ([], "requires at least one locus"),
        (
            [
                TranscriptLocus("ENST00000001", 10, 14),
                TranscriptLocus("ENST00000001", 10, 14),
            ],
            "duplicate loci",
        ),
        (
            [
                TranscriptLocus("ENST00000001", 10, 14),
                TranscriptLocus("ENST00000002", 30, 35),
            ],
            "same length as the site sequence",
        ),
    ],
)
def test_transcript_site_rejects_invalid_locus_sets(loci, message):
    with pytest.raises(ValueError, match=message):
        TranscriptSite(loci=loci, sequence=Seq("ACGT"))


@pytest.mark.unit
def test_transcript_site_identity_uses_id_and_loci():
    locus = TranscriptLocus("ENST00000001", 10, 14)
    first = TranscriptSite(id="site", loci=[locus], sequence=Seq("ACGT"))
    same_identity = TranscriptSite(
        id="site",
        loci=[locus],
        sequence=Seq("TGCA"),
    )
    different_locus = TranscriptSite(
        id="site",
        loci=[TranscriptLocus("ENST00000002", 20, 24)],
        sequence=Seq("ACGT"),
    )

    assert first == same_identity
    assert first != different_locus


@pytest.mark.unit
def test_transcript_site_does_not_project_itself_to_the_genome():
    site = TranscriptSite(
        loci=[TranscriptLocus("ENST00000001", 10, 14)],
        sequence=Seq("ACGT"),
    )

    assert not hasattr(site, "to_genomic_coordinates")
