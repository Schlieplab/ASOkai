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

from ASOkai.Antisense import (
    ASO,
    ASOCandidateGenerator,
    AntisenseCandidateGenerator,
    AntisenseTherapeutic,
)
from ASOkai.Biochemistry import GapmerChemistry, RNaseH1Mechanism
from ASOkai.Sites import Site, TranscriptSite


class TwoCandidateGenerator(AntisenseCandidateGenerator):
    def __init__(self):
        self.chemistry = GapmerChemistry("3-6-3")
        self.mechanism = RNaseH1Mechanism()

    def candidates_for_site(self, site: Site) -> list[AntisenseTherapeutic]:
        sequence = site.sequence.reverse_complement()
        return [
            ASO(
                id=f"{site.id}-ASO-1",
                sequence=sequence,
                chemistry=self.chemistry,
                mechanism=self.mechanism,
            ),
            ASO(
                id=f"{site.id}-ASO-2",
                sequence=sequence,
                chemistry=self.chemistry,
                mechanism=self.mechanism,
            ),
        ]


def test_aso_generator_creates_a_therapeutic_and_binding_for_each_site():
    site = TranscriptSite(
        id="target-S00001",
        transcript_id="transcript-1",
        t_start=0,
        t_end=12,
        sequence=Seq("ATGCCCAAAAAT"),
    )
    generator = ASOCandidateGenerator(
        chemistry=GapmerChemistry("3-6-3"),
        mechanism=RNaseH1Mechanism(),
    )

    therapeutics, bindings = generator.generate([site])

    assert len(therapeutics) == 1
    assert len(bindings) == 1
    assert therapeutics[0].id == "target-S00001-ASO-gapmer-3-6-3"
    assert therapeutics[0].sequence == Seq("ATTTTTGGGCAT")
    assert bindings[0].therapeutic_id == therapeutics[0].id
    assert bindings[0].site_id == site.id


def test_generator_supports_multiple_candidates_for_one_site():
    site = TranscriptSite(
        id="target-S00001",
        transcript_id="transcript-1",
        t_start=0,
        t_end=12,
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
        transcript_id="transcript-1",
        t_start=0,
        t_end=12,
        sequence=Seq("ATGCCCAAAAAT"),
    )
    second_site = TranscriptSite(
        id="target-S00002",
        transcript_id="transcript-1",
        t_start=12,
        t_end=24,
        sequence=Seq("CCCCAAAATTTT"),
    )
    generator = ASOCandidateGenerator(
        chemistry=GapmerChemistry("3-6-3"),
        mechanism=RNaseH1Mechanism(),
    )

    therapeutics, bindings = generator.generate([first_site, second_site])

    assert len(therapeutics) == 2
    assert [
        (binding.therapeutic_id, binding.site_id) for binding in bindings
    ] == [
        (therapeutics[0].id, first_site.id),
        (therapeutics[1].id, second_site.id),
    ]


def test_generator_returns_empty_collections_without_sites():
    generator = ASOCandidateGenerator(
        chemistry=GapmerChemistry("3-6-3"),
        mechanism=RNaseH1Mechanism(),
    )

    therapeutics, bindings = generator.generate([])

    assert therapeutics == []
    assert bindings == []
