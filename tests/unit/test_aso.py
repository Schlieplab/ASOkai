#!/usr/bin/env python
"""
Filename: tests/unit/test_aso.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Tests for antisense oligonucleotide domain classes.
License: LGPL-3.0-or-later
"""

import inspect

from Bio.Seq import Seq
import pytest

from ASOkai.Antisense import (
    ASO,
    AntisenseTherapeutic,
    BasePair,
    Binding,
    Oligonucleotide,
    siRNA,
)
from ASOkai.Biochemistry import Chemistry, MechanismOfAction


def make_mechanism():
    return MechanismOfAction("example-mechanism")


def make_sirna(
    guide: Oligonucleotide,
    passenger: Oligonucleotide,
) -> siRNA:
    binding = Binding.from_pairs(
        guide.sequence,
        passenger.sequence,
        [
            BasePair(index, len(passenger.sequence) - index - 1)
            for index in range(len(guide.sequence))
        ],
    )
    return siRNA(
        antisense_strand=guide,
        sense_strand=passenger,
        mechanism=make_mechanism(),
        binding=binding,
    )


def test_aso_combines_oligonucleotide_and_therapeutic_contracts():
    assert issubclass(ASO, Oligonucleotide)
    assert issubclass(ASO, AntisenseTherapeutic)


def test_antisense_therapeutic_is_abstract():
    assert inspect.isabstract(AntisenseTherapeutic)


def test_mechanisms_are_id_only_values_with_nonempty_ids():
    mechanism = make_mechanism()
    assert mechanism == MechanismOfAction("example-mechanism")
    assert mechanism.to_dict()["id"] == "example-mechanism"
    with pytest.raises(ValueError, match="non-empty"):
        MechanismOfAction("")


def test_new_therapeutic_types_must_define_their_design_id():
    class FutureTherapeutic(AntisenseTherapeutic):
        @property
        def antisense_strand(self) -> Oligonucleotide:
            return Oligonucleotide(Seq("ACGT"))

    assert inspect.isabstract(FutureTherapeutic)
    with pytest.raises(TypeError, match="_design_id"):
        FutureTherapeutic()


def test_oligonucleotide_requires_a_sequence():
    with pytest.raises(ValueError, match="sequence cannot be empty"):
        Oligonucleotide(sequence=Seq(""))


def test_chemistry_is_optional_and_changes_aso_identity():
    mechanism = make_mechanism()
    bare = ASO(sequence=Seq("ATGC"), mechanism=mechanism)
    chemistry = Chemistry("example-chemistry")
    modified = ASO(
        sequence=Seq("ATGC"), mechanism=mechanism, chemistry=chemistry
    )

    assert bare.chemistry is None
    assert modified.chemistry is chemistry
    assert modified.id == f"{bare.id}-c17:{chemistry.id}"
    assert ASO.from_dict(modified.to_dict()).id == modified.id


def test_each_sirna_strand_chemistry_changes_duplex_identity():
    bare = make_sirna(
        Oligonucleotide(Seq("ATGC")),
        Oligonucleotide(Seq("GCAT")),
    )
    antisense_modified = make_sirna(
        Oligonucleotide(
            Seq("ATGC"), chemistry=Chemistry("example-chemistry")
        ),
        Oligonucleotide(Seq("GCAT")),
    )
    sense_modified = make_sirna(
        Oligonucleotide(Seq("ATGC")),
        Oligonucleotide(
            Seq("GCAT"), chemistry=Chemistry("example-chemistry")
        ),
    )

    assert len({bare.id, antisense_modified.id, sense_modified.id}) == 3
    assert siRNA.from_dict(antisense_modified.to_dict()).id == (
        antisense_modified.id
    )


def test_optional_attachments_require_nonempty_ids():
    with pytest.raises(ValueError, match="Chemistry ID"):
        Chemistry("")


def test_optional_attachments_require_their_declared_types():
    with pytest.raises(TypeError, match="chemistry must be Chemistry"):
        Oligonucleotide(Seq("ACGT"), chemistry="lna")


def test_aso_is_its_own_antisense_strand():
    aso = ASO(
        sequence=Seq("ATGC"),
        mechanism=make_mechanism(),
    )

    assert aso.antisense_strand is aso
    assert aso.sequence == Seq("ATGC")
    assert aso.id.startswith("aso:m")


def test_constructor_rejects_an_id_that_disagrees_with_the_design():
    with pytest.raises(ValueError, match="does not match design ID"):
        ASO(
            sequence=Seq("ATGC"),
            mechanism=make_mechanism(),
            id="unrelated-id",
        )


def test_sirna_sequence_is_the_antisense_sequence():
    antisense = Oligonucleotide(
        sequence=Seq("ATGC"),
    )
    sense = Oligonucleotide(
        sequence=Seq("GCAT"),
    )
    sirna = make_sirna(antisense, sense)

    assert sirna.sequence == antisense.sequence
    assert sirna.sense_strand.sequence == sense.sequence


def test_sirna_serialization_roundtrip():
    sirna = make_sirna(
        Oligonucleotide(
            sequence=Seq("ATGC"),
        ),
        Oligonucleotide(
            sequence=Seq("GCAT"),
        ),
    )

    data = sirna.to_dict()
    reconstructed = siRNA.from_dict(data)

    assert "antisense_strand" in data
    assert "sense_strand" in data
    assert "binding" in data
    assert "_antisense_strand" not in data
    assert "_sense_strand" not in data
    assert "id" not in data["antisense_strand"]
    assert "id" not in data["sense_strand"]
    assert isinstance(reconstructed, siRNA)
    assert reconstructed.sequence == sirna.sequence
    assert reconstructed.sense_strand.sequence == sirna.sense_strand.sequence
    assert reconstructed.binding.pairs == sirna.binding.pairs
    assert reconstructed.mechanism == make_mechanism()


def test_sirna_rejects_a_binding_for_different_strands():
    with pytest.raises(ValueError, match="must match"):
        siRNA(
            antisense_strand=Oligonucleotide(Seq("ATGC")),
            sense_strand=Oligonucleotide(Seq("GCAT")),
            mechanism=make_mechanism(),
            binding=Binding.from_pairs(
                Seq("AAAA"),
                Seq("GCAT"),
                [BasePair(i, 3 - i) for i in range(4)],
            ),
        )
