#!/usr/bin/env python
"""
Filename: tests/unit/test_antisense_file_contracts.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Tests for typed antisense JSON file contracts.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

import json
from typing import Any, cast

from Bio.Seq import Seq
import pytest

from ASOkai.Antisense import (
    ASO,
    AntisenseTherapeutic,
    BasePair,
    Binding,
    Gapmer,
    Oligonucleotide,
    siRNA,
)
from ASOkai.Biochemistry import Chemistry, MechanismOfAction
from ASOkai.Plugins import JsonFile
from ASOkai._pipeline.steps.core.generate_therapeutic_candidates import (
    GenerateTherapeuticCandidatesStep,
)


@pytest.fixture
def gapmer() -> Gapmer:
    return Gapmer(
        sequence=Seq("ACGT"),
        mechanism=MechanismOfAction("rnase-h1"),
        left_wing_length=1,
        gap_length=2,
        right_wing_length=1,
    )


@pytest.fixture
def aso() -> ASO:
    return ASO(
        sequence=Seq("ACGT"),
        mechanism=MechanismOfAction("rnase-h1"),
    )


@pytest.fixture
def sirna() -> siRNA:
    return _make_sirna(
        Oligonucleotide(sequence=Seq("ACGT")),
        Oligonucleotide(sequence=Seq("TGCA")),
    )


def _make_sirna(guide: Oligonucleotide, passenger: Oligonucleotide) -> siRNA:
    return siRNA(
        antisense_strand=guide,
        sense_strand=passenger,
        mechanism=MechanismOfAction("rnase-h1"),
        binding=Binding.from_pairs(
            guide.sequence,
            passenger.sequence,
            [
                BasePair(index, len(passenger.sequence) - index - 1)
                for index in range(len(guide.sequence))
            ],
        ),
    )


def _site_binding() -> Binding:
    return Binding.from_complementary_sequences(
        Seq("ACGT"),
        Seq("ACGT"),
        first_id="aso:1",
        second_id="site:1",
    )


def test_step_declares_typed_antisense_collections():
    therapeutics_file = (
        GenerateTherapeuticCandidatesStep.therapeutics_output.file_type
    )
    bindings_file = GenerateTherapeuticCandidatesStep.bindings_output.file_type

    assert isinstance(therapeutics_file, JsonFile)
    assert isinstance(bindings_file, JsonFile)
    assert therapeutics_file.value_type == list[AntisenseTherapeutic]
    assert bindings_file.value_type == list[Binding]


def _assert_therapeutic_roundtrip(therapeutic: AntisenseTherapeutic) -> None:
    file_type = GenerateTherapeuticCandidatesStep.therapeutics_output.file_type

    restored = file_type.loads(file_type.dumps([therapeutic]))

    assert len(restored) == 1
    assert type(restored[0]) is type(therapeutic)
    assert restored[0].id == therapeutic.id
    assert str(restored[0].sequence) == str(therapeutic.sequence)
    assert isinstance(restored[0].mechanism, MechanismOfAction)


def test_aso_collection_roundtrip_reconstructs_domain_values(aso):
    _assert_therapeutic_roundtrip(aso)


def test_gapmer_collection_roundtrip_reconstructs_domain_values(gapmer):
    _assert_therapeutic_roundtrip(gapmer)
    file_type = GenerateTherapeuticCandidatesStep.therapeutics_output.file_type

    restored = file_type.loads(file_type.dumps([gapmer]))

    assert restored[0].layout == gapmer.layout


def test_sirna_collection_roundtrip_reconstructs_domain_values(sirna):
    _assert_therapeutic_roundtrip(sirna)
    file_type = GenerateTherapeuticCandidatesStep.therapeutics_output.file_type

    restored = file_type.loads(file_type.dumps([sirna]))

    assert restored[0].antisense_strand.sequence == Seq("ACGT")
    assert restored[0].sense_strand.sequence == Seq("TGCA")
    assert restored[0].binding.pairs == sirna.binding.pairs


def test_optional_chemistry_survives_graph_roundtrip():
    therapeutic = _make_sirna(
        Oligonucleotide(
            Seq("ACGT"), chemistry=Chemistry("lna")
        ),
        Oligonucleotide(
            Seq("TGCA"), chemistry=Chemistry("pna")
        ),
    )
    file_type = GenerateTherapeuticCandidatesStep.therapeutics_output.file_type

    restored = file_type.loads(file_type.dumps([therapeutic]))[0]

    assert restored.id == therapeutic.id
    assert restored.antisense_strand.chemistry.id == "lna"
    assert restored.sense_strand.chemistry.id == "pna"


def test_shared_strand_chemistry_remains_one_object_after_graph_roundtrip():
    chemistry = Chemistry("lna")
    therapeutic = _make_sirna(
        Oligonucleotide(Seq("ACGT"), chemistry=chemistry),
        Oligonucleotide(Seq("TGCA"), chemistry=chemistry),
    )
    file_type = GenerateTherapeuticCandidatesStep.therapeutics_output.file_type

    restored = file_type.loads(file_type.dumps([therapeutic]))[0]

    assert restored.antisense_strand.chemistry is restored.sense_strand.chemistry


@pytest.mark.parametrize("therapeutic_name", ["aso", "gapmer", "sirna"])
def test_therapeutic_collection_rejects_mismatched_stored_id(
    request, therapeutic_name,
):
    therapeutic = request.getfixturevalue(therapeutic_name)
    file_type = GenerateTherapeuticCandidatesStep.therapeutics_output.file_type
    document = json.loads(file_type.dumps([therapeutic]))
    document["root"][0]["id"] = "unrelated-id"

    with pytest.raises(ValueError, match="does not match design ID"):
        file_type.loads(json.dumps(document))


def test_binding_collection_roundtrip_reconstructs_domain_values():
    file_type = GenerateTherapeuticCandidatesStep.bindings_output.file_type
    binding = _site_binding()

    restored = file_type.loads(file_type.dumps([binding]))

    assert len(restored) == 1
    assert isinstance(restored[0], Binding)
    assert restored[0].first_sequence == binding.first_sequence
    assert restored[0].second_sequence == binding.second_sequence
    assert restored[0].first_id == binding.first_id
    assert restored[0].second_id == binding.second_id
    assert restored[0].pairs == binding.pairs


def test_therapeutic_collection_preserves_one_shared_mechanism():
    mechanism = MechanismOfAction("rnase-h1")
    therapeutics = [
        ASO(sequence=Seq("ACGT"), mechanism=mechanism),
        ASO(sequence=Seq("CGTA"), mechanism=mechanism),
    ]
    file_type = GenerateTherapeuticCandidatesStep.therapeutics_output.file_type

    document = json.loads(file_type.dumps(therapeutics))

    assert document["root"][0]["mechanism"] == {
        "$ref": "#/objects/MechanismOfAction"
    }
    assert document["root"][1]["mechanism"] == {
        "$ref": "#/objects/MechanismOfAction"
    }
    assert list(document["objects"]) == ["MechanismOfAction"]
    assert sum(
        record.get("__class__") == "MechanismOfAction"
        for record in document["objects"].values()
    ) == 1

    restored = file_type.loads(json.dumps(document))

    assert restored[0].mechanism is restored[1].mechanism


def test_gapmer_collection_rejects_a_layout_length_mismatch(gapmer):
    file_type = GenerateTherapeuticCandidatesStep.therapeutics_output.file_type
    document = json.loads(file_type.dumps([gapmer]))
    document["root"][0]["gap_length"] = 1

    with pytest.raises(ValueError, match="must equal the sequence length"):
        file_type.loads(json.dumps(document))


def test_binding_collection_rejects_invalid_ids():
    file_type = GenerateTherapeuticCandidatesStep.bindings_output.file_type
    document = json.loads(file_type.dumps([_site_binding()]))
    document["root"][0]["second_id"] = []

    with pytest.raises(ValueError, match=r"\$.root\[0\].second_id"):
        file_type.loads(json.dumps(document))


def test_typed_collection_schema_rejects_the_wrong_item_type():
    file_type = GenerateTherapeuticCandidatesStep.therapeutics_output.file_type
    with pytest.raises(ValueError, match=r"\$.root\[0\]"):
        file_type.dumps(cast(Any, [_site_binding()]))
