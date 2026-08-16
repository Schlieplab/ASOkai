#!/usr/bin/env python
"""
Filename: tests/unit/test_transcript_site_functionality.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Version: 0.1.1
Description: Functional tests for TranscriptSite.
License: LGPL-3.0-or-later
"""

import pytest
from Bio.Seq import Seq
from GenomeUtils.Genome import TranscriptLocus

from ASOkai.Sites import TranscriptSite


@pytest.mark.unit
def test_transcript_site_can_belong_to_multiple_transcripts():
    loci = [
        TranscriptLocus("ENST00000002", 30, 34),
        TranscriptLocus("ENST00000001", 10, 14),
    ]

    site = TranscriptSite(
        id="shared-site",
        loci=loci,
        sequence=Seq("ACGT"),
    )

    assert site.id == "shared-site"
    assert site.loci == sorted(loci)
    assert site.sequence == Seq("ACGT")


@pytest.mark.unit
def test_transcript_site_copies_its_locus_list():
    loci = [TranscriptLocus("ENST00000001", 10, 14)]
    site = TranscriptSite(loci=loci, sequence=Seq("ACGT"))

    loci.append(TranscriptLocus("ENST00000002", 30, 34))

    assert site.loci == [TranscriptLocus("ENST00000001", 10, 14)]


@pytest.mark.unit
def test_transcript_site_derives_id_from_its_first_locus():
    site = TranscriptSite(
        loci=[TranscriptLocus("ENST00000001", 10, 14)],
        sequence=Seq("ACGT"),
    )

    assert site.id == "ENST00000001:10-14"


@pytest.mark.unit
def test_transcript_site_requires_a_locus():
    with pytest.raises(
        ValueError,
        match="requires at least one locus",
    ):
        TranscriptSite(loci=[], sequence=Seq("ACGT"))


@pytest.mark.unit
def test_transcript_site_rejects_duplicate_loci():
    locus = TranscriptLocus("ENST00000001", 10, 14)

    with pytest.raises(ValueError, match="duplicate loci"):
        TranscriptSite(loci=[locus, locus], sequence=Seq("ACGT"))


@pytest.mark.unit
def test_transcript_site_requires_every_locus_to_match_sequence_length():
    with pytest.raises(
        ValueError,
        match="same length as the site sequence",
    ):
        TranscriptSite(
            loci=[
                TranscriptLocus("ENST00000001", 10, 14),
                TranscriptLocus("ENST00000002", 30, 35),
            ],
            sequence=Seq("ACGT"),
        )


@pytest.mark.unit
def test_transcript_site_preserves_additional_attributes():
    site = TranscriptSite(
        loci=[TranscriptLocus("ENST00000001", 10, 14)],
        sequence=Seq("ACGT"),
        score=0.75,
    )

    assert getattr(site, "score") == 0.75


@pytest.mark.unit
def test_transcript_site_equality_uses_id_and_loci():
    locus = TranscriptLocus("ENST00000001", 10, 14)
    first = TranscriptSite(id="site", loci=[locus], sequence=Seq("ACGT"))
    second = TranscriptSite(id="site", loci=[locus], sequence=Seq("ACGT"))
    other_locus = TranscriptSite(
        id="site",
        loci=[TranscriptLocus("ENST00000002", 20, 24)],
        sequence=Seq("ACGT"),
    )

    assert first == second
    assert first != other_locus
    assert (first == "site") is False


@pytest.mark.unit
def test_transcript_site_does_not_project_itself_to_the_genome():
    site = TranscriptSite(
        loci=[TranscriptLocus("ENST00000001", 10, 14)],
        sequence=Seq("ACGT"),
    )

    assert not hasattr(site, "to_genomic_coordinates")
