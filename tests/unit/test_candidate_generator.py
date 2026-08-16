#!/usr/bin/env python
"""
Filename: tests/unit/test_candidate_generator.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Version: 0.1.1
Description: Tests for antisense candidate generation.
License: LGPL-3.0-or-later
"""

from Bio.Seq import Seq
from GenomeUtils.Genome import TranscriptLocus

from ASOkai.Antisense import (
    ASO,
    ASOCandidateGenerator,
    AntisenseCandidateGenerator,
    AntisenseTherapeutic,
    Gapmer,
    GapmerCandidateGenerator,
)
from ASOkai.Biochemistry import RNaseH1Mechanism
from ASOkai.Sites import Site, TranscriptSite


class TwoCandidateGenerator(AntisenseCandidateGenerator):
    def __init__(self):
        self.mechanism = RNaseH1Mechanism()

    def candidates_for_site(self, site: Site) -> list[AntisenseTherapeutic]:
        sequence = site.sequence.reverse_complement()
        return [
            ASO(
                id=f"{site.id}-ASO-1",
                sequence=sequence,
                mechanism=self.mechanism,
            ),
            ASO(
                id=f"{site.id}-ASO-2",
                sequence=sequence,
                mechanism=self.mechanism,
            ),
        ]


def test_gapmer_generator_creates_a_therapeutic_and_binding_for_each_site():
    site = TranscriptSite(
        id="target-S00001",
        loci=[TranscriptLocus("transcript-1", 0, 12)],
        sequence=Seq("ATGCCCAAAAAT"),
    )
    generator = GapmerCandidateGenerator(
        mechanism=RNaseH1Mechanism(),
        left_wing_length=3,
        gap_length=6,
        right_wing_length=3,
    )

    therapeutics, bindings = generator.generate([site])

    assert len(therapeutics) == 1
    assert len(bindings) == 1
    assert isinstance(therapeutics[0], Gapmer)
    assert therapeutics[0].id == "target-S00001-Gapmer"
    assert therapeutics[0].sequence == Seq("ATTTTTGGGCAT")
    assert therapeutics[0].layout == "3-6-3"
    assert bindings[0].therapeutic_id == therapeutics[0].id
    assert bindings[0].site_id == site.id


def test_generator_supports_multiple_candidates_for_one_site():
    site = TranscriptSite(
        id="target-S00001",
        loci=[TranscriptLocus("transcript-1", 0, 12)],
        sequence=Seq("ATGCCCAAAAAT"),
    )
    therapeutics, bindings = TwoCandidateGenerator().generate([site])

    assert [therapeutic.id for therapeutic in therapeutics] == [
        "target-S00001-ASO-1",
        "target-S00001-ASO-2",
    ]
    assert [binding.therapeutic_id for binding in bindings] == [
        "target-S00001-ASO-1",
        "target-S00001-ASO-2",
    ]
    assert [binding.site_id for binding in bindings] == [site.id, site.id]


def test_aso_generator_preserves_the_site_for_each_binding():
    first_site = TranscriptSite(
        id="target-S00001",
        loci=[TranscriptLocus("transcript-1", 0, 12)],
        sequence=Seq("ATGCCCAAAAAT"),
    )
    second_site = TranscriptSite(
        id="target-S00002",
        loci=[TranscriptLocus("transcript-1", 12, 24)],
        sequence=Seq("CCCCAAAATTTT"),
    )
    generator = ASOCandidateGenerator(mechanism=RNaseH1Mechanism())

    therapeutics, bindings = generator.generate([first_site, second_site])

    assert len(therapeutics) == 2
    assert [
        (binding.therapeutic_id, binding.site_id) for binding in bindings
    ] == [
        (therapeutics[0].id, first_site.id),
        (therapeutics[1].id, second_site.id),
    ]


def test_generator_returns_empty_collections_without_sites():
    generator = ASOCandidateGenerator(mechanism=RNaseH1Mechanism())

    therapeutics, bindings = generator.generate([])

    assert therapeutics == []
    assert bindings == []
