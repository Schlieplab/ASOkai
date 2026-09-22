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
    Binding,
    Gapmer,
    Oligonucleotide,
    siRNA,
)
from ASOkai.Biochemistry import RNaseH1Mechanism
from ASOkai.Plugins import JsonFile
from ASOkai._pipeline.steps.core.generate_aso_candidates import (
    GenerateASOCandidatesStep,
)


@pytest.fixture
def gapmer() -> Gapmer:
    return Gapmer(
        id="gapmer-1",
        sequence=Seq("ACGT"),
        mechanism=RNaseH1Mechanism(),
        left_wing_length=1,
        gap_length=2,
        right_wing_length=1,
    )


@pytest.fixture
def aso() -> ASO:
    return ASO(
        id="aso-1",
        sequence=Seq("ACGT"),
        mechanism=RNaseH1Mechanism(),
    )


@pytest.fixture
def sirna() -> siRNA:
    return siRNA(
        id="sirna-1",
        antisense_strand=Oligonucleotide(sequence=Seq("ACGT")),
        sense_strand=Oligonucleotide(sequence=Seq("TGCA")),
        mechanism=RNaseH1Mechanism(),
    )


def test_step_declares_typed_antisense_collections():
    therapeutics_file = (
        GenerateASOCandidatesStep.therapeutics_output.file_type
    )
    bindings_file = GenerateASOCandidatesStep.bindings_output.file_type

    assert isinstance(therapeutics_file, JsonFile)
    assert isinstance(bindings_file, JsonFile)
    assert therapeutics_file.value_type == list[AntisenseTherapeutic]
    assert bindings_file.value_type == list[Binding]


def _assert_therapeutic_roundtrip(therapeutic: AntisenseTherapeutic) -> None:
    file_type = GenerateASOCandidatesStep.therapeutics_output.file_type

    restored = file_type.loads(file_type.dumps([therapeutic]))

    assert len(restored) == 1
    assert type(restored[0]) is type(therapeutic)
    assert restored[0].id == therapeutic.id
    assert str(restored[0].sequence) == str(therapeutic.sequence)
    assert isinstance(restored[0].mechanism, RNaseH1Mechanism)


def test_aso_collection_roundtrip_reconstructs_domain_values(aso):
    _assert_therapeutic_roundtrip(aso)


def test_gapmer_collection_roundtrip_reconstructs_domain_values(gapmer):
    _assert_therapeutic_roundtrip(gapmer)
    file_type = GenerateASOCandidatesStep.therapeutics_output.file_type

    restored = file_type.loads(file_type.dumps([gapmer]))

    assert restored[0].layout == gapmer.layout


def test_sirna_collection_roundtrip_reconstructs_domain_values(sirna):
    _assert_therapeutic_roundtrip(sirna)
    file_type = GenerateASOCandidatesStep.therapeutics_output.file_type

    restored = file_type.loads(file_type.dumps([sirna]))

    assert restored[0].antisense_strand.sequence == Seq("ACGT")
    assert restored[0].sense_strand.sequence == Seq("TGCA")


def test_binding_collection_roundtrip_reconstructs_domain_values():
    file_type = GenerateASOCandidatesStep.bindings_output.file_type
    binding = Binding("aso-1", "site-1")

    restored = file_type.loads(file_type.dumps([binding]))

    assert len(restored) == 1
    assert isinstance(restored[0], Binding)
    assert restored[0].therapeutic_id == binding.therapeutic_id
    assert restored[0].site_id == binding.site_id


def test_therapeutic_collection_preserves_one_shared_mechanism():
    mechanism = RNaseH1Mechanism()
    therapeutics = [
        ASO(id="aso-1", sequence=Seq("ACGT"), mechanism=mechanism),
        ASO(id="aso-2", sequence=Seq("CGTA"), mechanism=mechanism),
    ]
    file_type = GenerateASOCandidatesStep.therapeutics_output.file_type

    document = json.loads(file_type.dumps(therapeutics))

    assert document["root"][0]["mechanism"] == {
        "$ref": "#/objects/RNaseH1Mechanism"
    }
    assert document["root"][1]["mechanism"] == {
        "$ref": "#/objects/RNaseH1Mechanism"
    }
    assert list(document["objects"]) == ["RNaseH1Mechanism"]
    assert sum(
        record.get("__class__") == "RNaseH1Mechanism"
        for record in document["objects"].values()
    ) == 1

    restored = file_type.loads(json.dumps(document))

    assert restored[0].mechanism is restored[1].mechanism


def test_gapmer_collection_rejects_a_layout_length_mismatch(gapmer):
    file_type = GenerateASOCandidatesStep.therapeutics_output.file_type
    document = json.loads(file_type.dumps([gapmer]))
    document["root"][0]["gap_length"] = 1

    with pytest.raises(ValueError, match="must equal the sequence length"):
        file_type.loads(json.dumps(document))


def test_binding_collection_rejects_invalid_ids():
    file_type = GenerateASOCandidatesStep.bindings_output.file_type
    document = json.loads(file_type.dumps([Binding("aso-1", "site-1")]))
    document["root"][0]["site_id"] = []

    with pytest.raises(ValueError, match=r"\$.root\[0\].site_id"):
        file_type.loads(json.dumps(document))


def test_typed_collection_schema_rejects_the_wrong_item_type():
    file_type = GenerateASOCandidatesStep.therapeutics_output.file_type

    with pytest.raises(ValueError, match=r"\$.root\[0\]"):
        file_type.dumps(cast(Any, [Binding("aso-1", "site-1")]))
