#!/usr/bin/env python
"""
Filename: tests/unit/test_candidate_generator.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
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
    Oligonucleotide,
    SiRNACandidateGenerator,
    siRNA,
)
from ASOkai.Biochemistry import MechanismOfAction
from ASOkai.Sites import Site, TranscriptSite


class TwoCandidateGenerator(AntisenseCandidateGenerator):
    def __init__(self):
        self.mechanism = MechanismOfAction("rnase-h1")

    def candidates_for_site(self, site: Site) -> list[AntisenseTherapeutic]:
        sequence = site.sequence.reverse_complement()
        return [
            ASO(
                sequence=sequence,
                mechanism=self.mechanism,
            ),
            Gapmer(
                sequence=sequence,
                mechanism=self.mechanism,
                left_wing_length=3,
                gap_length=6,
                right_wing_length=3,
            ),
        ]


def test_gapmer_generator_creates_a_therapeutic_and_binding_for_each_site():
    site = TranscriptSite(
        id="target-S00001",
        loci=[TranscriptLocus("transcript-1", 0, 12)],
        sequence=Seq("ATGCCCAAAAAT"),
    )
    generator = GapmerCandidateGenerator(
        mechanism=MechanismOfAction("rnase-h1"),
        left_wing_length=3,
        gap_length=6,
        right_wing_length=3,
    )

    therapeutics, bindings = generator.generate([site])

    assert len(therapeutics) == 1
    assert len(bindings) == 1
    assert isinstance(therapeutics[0], Gapmer)
    assert therapeutics[0].id.startswith("gapmer:l3g6r3-mrnase-h1-s12x")
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

    assert [type(therapeutic) for therapeutic in therapeutics] == [ASO, Gapmer]
    assert len({therapeutic.id for therapeutic in therapeutics}) == 2
    assert [binding.therapeutic_id for binding in bindings] == [
        therapeutic.id for therapeutic in therapeutics
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
    generator = ASOCandidateGenerator(mechanism=MechanismOfAction("rnase-h1"))

    therapeutics, bindings = generator.generate([first_site, second_site])

    assert len(therapeutics) == 2
    assert all(isinstance(therapeutic, ASO) for therapeutic in therapeutics)
    assert len({therapeutic.id for therapeutic in therapeutics}) == 2
    assert all(
        therapeutic.id.startswith("aso:mrnase-h1-s12x")
        for therapeutic in therapeutics
    )
    assert [therapeutic.sequence for therapeutic in therapeutics] == [
        first_site.sequence.reverse_complement(),
        second_site.sequence.reverse_complement(),
    ]
    assert [
        (binding.therapeutic_id, binding.site_id) for binding in bindings
    ] == [
        (therapeutics[0].id, first_site.id),
        (therapeutics[1].id, second_site.id),
    ]


def test_sirna_generator_creates_an_antiparallel_duplex_for_each_site():
    site = TranscriptSite(
        id="target-S00001",
        loci=[TranscriptLocus("transcript-1", 0, 4)],
        sequence=Seq("ATGC"),
    )
    generator = SiRNACandidateGenerator(
        mechanism=MechanismOfAction("rna-interference")
    )

    therapeutics, bindings = generator.generate([site])

    assert len(therapeutics) == 1
    therapeutic = therapeutics[0]
    assert isinstance(therapeutic, siRNA)
    assert isinstance(therapeutic.antisense_strand, Oligonucleotide)
    assert therapeutic.id.startswith("sirna:m")
    assert therapeutic.id.endswith("-as4x93-ps4x39")
    assert therapeutic.antisense_strand.sequence == Seq("GCAT")
    assert therapeutic.sense_strand.sequence == Seq("ATGC")
    assert len(bindings) == 1
    assert bindings[0].therapeutic_id == therapeutic.id
    assert bindings[0].site_id == site.id


def test_generator_returns_empty_collections_without_sites():
    generator = ASOCandidateGenerator(mechanism=MechanismOfAction("rnase-h1"))

    therapeutics, bindings = generator.generate([])

    assert therapeutics == []
    assert bindings == []


def test_same_design_from_two_sites_has_one_therapeutic_and_two_bindings():
    sites = [
        TranscriptSite(
            id=f"site-{number}",
            loci=[TranscriptLocus(f"transcript-{number}", 0, 4)],
            sequence=Seq("ACGT"),
        )
        for number in (1, 2)
    ]

    therapeutics, bindings = ASOCandidateGenerator(
        MechanismOfAction("rnase-h1")
    ).generate(sites)

    assert len(therapeutics) == 1
    assert [(binding.therapeutic_id, binding.site_id) for binding in bindings] == [
        (therapeutics[0].id, "site-1"),
        (therapeutics[0].id, "site-2"),
    ]


def test_design_id_distinguishes_layout_mechanism_and_sequence():
    mechanism = MechanismOfAction("rnase-h1")
    other_mechanism = MechanismOfAction("rna-interference")

    def aso(sequence, mechanism=mechanism):
        return ASO(sequence=Seq(sequence), mechanism=mechanism)

    assert aso("ACGT").id == "aso:mrnase-h1-s4x1b"
    assert aso("A").id != aso("AA").id
    assert aso("AN").id != aso("AA").id
    assert aso("a").id != aso("A").id
    assert aso("ACGT").id != aso("ACGT", other_mechanism).id
    first_gapmer = Gapmer(
        sequence=Seq("ACGT"), mechanism=mechanism,
        left_wing_length=1, gap_length=2, right_wing_length=1,
    )
    second_gapmer = Gapmer(
        sequence=Seq("ACGT"), mechanism=mechanism,
        left_wing_length=1, gap_length=1, right_wing_length=2,
    )
    assert first_gapmer.id != second_gapmer.id
    first_sirna = siRNA(
        antisense_strand=Oligonucleotide(Seq("ACGT")),
        sense_strand=Oligonucleotide(Seq("TGCA")),
        mechanism=mechanism,
    )
    second_sirna = siRNA(
        antisense_strand=Oligonucleotide(Seq("ACGT")),
        sense_strand=Oligonucleotide(Seq("AAAA")),
        mechanism=mechanism,
    )
    assert first_sirna.id != second_sirna.id
