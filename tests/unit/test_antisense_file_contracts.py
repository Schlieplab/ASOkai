#!/usr/bin/env python
"""Tests for typed antisense JSON file contracts."""

from __future__ import annotations

import json
from typing import Any, cast

from Bio.Seq import Seq
import pytest

from ASOkai.Antisense import ASO, Binding
from ASOkai.Biochemistry import GapmerChemistry, RNaseH1Mechanism
from ASOkai.Plugins import JsonFile
from ASOkai._pipeline.steps.core.generate_antisense_candidates import (
    GenerateAntisenseCandidatesStep,
)


@pytest.fixture
def aso() -> ASO:
    return ASO(
        id="aso-1",
        sequence=Seq("ACGT"),
        chemistry=GapmerChemistry("1-2-1"),
        mechanism=RNaseH1Mechanism(),
    )


def test_step_declares_typed_antisense_collections():
    therapeutics_file = (
        GenerateAntisenseCandidatesStep.therapeutics_output.file_type
    )
    bindings_file = GenerateAntisenseCandidatesStep.bindings_output.file_type

    assert isinstance(therapeutics_file, JsonFile)
    assert isinstance(bindings_file, JsonFile)
    assert therapeutics_file.value_type == list[ASO]
    assert bindings_file.value_type == list[Binding]


def test_aso_collection_roundtrip_reconstructs_domain_values(aso):
    file_type = GenerateAntisenseCandidatesStep.therapeutics_output.file_type

    restored = file_type.loads(file_type.dumps([aso]))

    assert len(restored) == 1
    assert isinstance(restored[0], ASO)
    assert restored[0].id == aso.id
    assert str(restored[0].sequence) == str(aso.sequence)
    assert isinstance(restored[0].chemistry, GapmerChemistry)
    assert isinstance(restored[0].mechanism, RNaseH1Mechanism)


def test_binding_collection_roundtrip_reconstructs_domain_values():
    file_type = GenerateAntisenseCandidatesStep.bindings_output.file_type
    binding = Binding("aso-1", "site-1")

    restored = file_type.loads(file_type.dumps([binding]))

    assert len(restored) == 1
    assert isinstance(restored[0], Binding)
    assert restored[0].therapeutic_id == binding.therapeutic_id
    assert restored[0].site_id == binding.site_id


def test_aso_collection_rejects_invalid_nested_chemistry(aso):
    file_type = GenerateAntisenseCandidatesStep.therapeutics_output.file_type
    document = json.loads(file_type.dumps([aso]))
    document[0]["chemistry"]["layout"] = "invalid"

    with pytest.raises(ValueError, match="Gapmer layout must have the form"):
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
