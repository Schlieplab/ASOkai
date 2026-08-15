#!/usr/bin/env python
"""Tests for typed antisense JSON file contracts."""

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
from ASOkai._pipeline.steps.core.generate_antisense_candidates import (
    GenerateAntisenseCandidatesStep,
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
        GenerateAntisenseCandidatesStep.therapeutics_output.file_type
    )
    bindings_file = GenerateAntisenseCandidatesStep.bindings_output.file_type

    assert isinstance(therapeutics_file, JsonFile)
    assert isinstance(bindings_file, JsonFile)
    assert therapeutics_file.value_type == list[AntisenseTherapeutic]
    assert bindings_file.value_type == list[Binding]


def _assert_therapeutic_roundtrip(therapeutic: AntisenseTherapeutic) -> None:
    file_type = GenerateAntisenseCandidatesStep.therapeutics_output.file_type

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
    file_type = GenerateAntisenseCandidatesStep.therapeutics_output.file_type

    restored = file_type.loads(file_type.dumps([gapmer]))

    assert restored[0].layout == gapmer.layout


def test_sirna_collection_roundtrip_reconstructs_domain_values(sirna):
    _assert_therapeutic_roundtrip(sirna)
    file_type = GenerateAntisenseCandidatesStep.therapeutics_output.file_type

    restored = file_type.loads(file_type.dumps([sirna]))

    assert restored[0].antisense_strand.sequence == Seq("ACGT")
    assert restored[0].sense_strand.sequence == Seq("TGCA")


def test_binding_collection_roundtrip_reconstructs_domain_values():
    file_type = GenerateAntisenseCandidatesStep.bindings_output.file_type
    binding = Binding("aso-1", "site-1")

    restored = file_type.loads(file_type.dumps([binding]))

    assert len(restored) == 1
    assert isinstance(restored[0], Binding)
    assert restored[0].therapeutic_id == binding.therapeutic_id
    assert restored[0].site_id == binding.site_id


def test_gapmer_collection_rejects_invalid_segment_length(gapmer):
    file_type = GenerateAntisenseCandidatesStep.therapeutics_output.file_type
    document = json.loads(file_type.dumps([gapmer]))
    document[0]["gap_length"] = 0

    with pytest.raises(ValueError, match="Gapmer gap_length"):
        file_type.loads(json.dumps(document))


def test_binding_collection_rejects_invalid_ids():
    file_type = GenerateAntisenseCandidatesStep.bindings_output.file_type
    document = json.loads(file_type.dumps([Binding("aso-1", "site-1")]))
    document[0]["site_id"] = []

    with pytest.raises(ValueError, match=r"\$\[0\]\.site_id"):
        file_type.loads(json.dumps(document))


def test_typed_collection_schema_rejects_the_wrong_item_type():
    file_type = GenerateAntisenseCandidatesStep.therapeutics_output.file_type

    with pytest.raises(ValueError, match=r"\$\[0\]"):
        file_type.dumps(cast(Any, [Binding("aso-1", "site-1")]))
