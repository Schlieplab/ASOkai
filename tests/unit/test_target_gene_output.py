#!/usr/bin/env python
"""
Filename: tests/unit/test_target_gene_output.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Tests for typed target-gene JSON inputs and outputs.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

import argparse
import json
from typing import Any, cast

from Bio.Seq import Seq
from GenomeUtils.Genome import TranscriptLocus
import pytest

from ASOkai.Sites import GenomicSite, TranscriptSite
from ASOkai.Targets import TargetGene
from ASOkai.Plugins import FileInput, FileOutput, JsonFile
from ASOkai._pipeline.steps.core.create_target_gene import CreateTargetGeneStep
from ASOkai._pipeline.steps.core.generate_therapeutic_candidates import (
    GenerateTherapeuticCandidatesStep,
)


@pytest.fixture
def output() -> FileOutput:
    return CreateTargetGeneStep.target_gene_output


@pytest.fixture
def input_contract() -> FileInput:
    return GenerateTherapeuticCandidatesStep.target_gene_input


@pytest.fixture
def target_gene() -> TargetGene:
    genomic = GenomicSite(
        id="genomic-site",
        chr="12",
        start=1,
        end=4,
        strand="+",
        sequence=Seq("ACGT"),
    )
    transcript = TranscriptSite(
        id="transcript-site",
        loci=[TranscriptLocus("ENST00000001", 4, 8)],
        sequence=Seq("TGCA"),
    )
    return TargetGene(
        id="ENSG00000001",
        name="TARGET",
        chr="12",
        start=1,
        end=8,
        strand="+",
        sequence=Seq("ACGTTGCA"),
        sites={
            genomic.id: genomic,
            transcript.id: transcript,
        },
    )


def test_steps_declare_target_gene_as_the_json_value_type(
    output,
    input_contract,
):
    assert isinstance(output.file_type, JsonFile)
    assert output.file_type.value_type is TargetGene
    assert input_contract.file_type is output.file_type
    assert output.file_type.media_type == "application/json"


def test_target_gene_roundtrip_uses_the_graph_serializable_shape(
    output,
    input_contract,
    target_gene,
):
    content = output.dumps(target_gene)
    payload = json.loads(content)

    target_record = payload["root"]
    assert payload["objects"] == {}
    assert target_record["__class__"] == "TargetGene"
    assert target_record["__module__"] == "ASOkai.Targets._target_gene"
    assert set(target_record["sites"]) == {"genomic-site", "transcript-site"}
    assert target_record["sites"]["genomic-site"]["__class__"] == "GenomicSite"
    assert target_record["sites"]["transcript-site"]["__class__"] == "TranscriptSite"
    assert "schema" not in payload
    assert content.endswith("\n")

    restored = input_contract.loads(content)

    assert isinstance(restored, TargetGene)
    assert restored.id == target_gene.id
    assert str(restored.sequence) == str(target_gene.sequence)
    assert isinstance(restored.site_by_id("genomic-site"), GenomicSite)
    assert isinstance(restored.site_by_id("transcript-site"), TranscriptSite)


def test_target_gene_output_and_input_write_and_read_path(
    output,
    input_contract,
    target_gene,
    tmp_path,
):
    path = tmp_path / "target.json"
    output.write(path, target_gene)

    restored = input_contract.read(path)

    assert isinstance(restored, TargetGene)
    assert restored.id == target_gene.id
    assert path.read_text(encoding="utf-8") == output.dumps(target_gene)


def test_json_input_loads_an_existing_override_during_argument_parsing(
    output,
    input_contract,
    target_gene,
    tmp_path,
):
    path = tmp_path / "existing-target.json"
    output.write(path, target_gene)
    parser = argparse.ArgumentParser()
    input_contract.add_to_parser(parser)

    args = parser.parse_args(["--target-gene", str(path)])

    assert isinstance(args.target_gene, TargetGene)
    assert args.target_gene.id == target_gene.id


def test_target_gene_input_rejects_the_wrong_root_type(
    output,
    input_contract,
    target_gene,
):
    payload = json.loads(output.dumps(target_gene))
    payload["root"]["__class__"] = "Other"

    with pytest.raises(ValueError, match=r"\$.root.__class__"):
        input_contract.loads(json.dumps(payload))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("name", 42),
        ("start", True),
        ("strand", "?"),
        ("sequence", 42),
    ],
)
def test_target_gene_input_rejects_invalid_core_fields(
    output,
    input_contract,
    target_gene,
    field,
    value,
):
    payload = json.loads(output.dumps(target_gene))
    payload["root"][field] = value

    with pytest.raises(ValueError, match=rf"\$.root.{field}"):
        input_contract.loads(json.dumps(payload))


def test_target_gene_input_rejects_site_key_mismatch(
    output,
    input_contract,
    target_gene,
):
    payload = json.loads(output.dumps(target_gene))
    sites = payload["root"]["sites"]
    sites["wrong-key"] = sites.pop("genomic-site")

    with pytest.raises(ValueError, match="must match site ID 'genomic-site'"):
        input_contract.loads(json.dumps(payload))


def test_target_gene_input_rejects_non_site_values(
    output,
    input_contract,
    target_gene,
):
    payload = json.loads(output.dumps(target_gene))
    payload["root"]["sites"]["not-a-site"] = 42

    with pytest.raises(
        ValueError,
        match=r"\$.root.sites.not-a-site",
    ):
        input_contract.loads(json.dumps(payload))


@pytest.mark.parametrize(
    ("site_id", "field"),
    [
        (None, "genome"),
        (None, "chromosome"),
        ("genomic-site", "genome"),
    ],
)
def test_target_gene_input_rejects_invalid_runtime_references(
    output,
    input_contract,
    target_gene,
    site_id,
    field,
):
    payload = json.loads(output.dumps(target_gene))
    destination = (
        payload["root"]
        if site_id is None
        else payload["root"]["sites"]["genomic-site"]
    )
    destination[field] = "not-a-genome"

    with pytest.raises(ValueError) as raised:
        input_contract.loads(json.dumps(payload))

    assert field in str(raised.value)


def test_target_gene_schema_reports_all_structural_errors(
    output,
    input_contract,
    target_gene,
):
    payload = json.loads(output.dumps(target_gene))
    target_record = payload["root"]
    target_record["name"] = []
    target_record["start"] = True

    with pytest.raises(ValueError) as raised:
        input_contract.loads(json.dumps(payload))

    assert "$.root.name" in str(raised.value)
    assert "$.root.start" in str(raised.value)


def test_target_gene_input_preserves_extra_metadata(
    output,
    input_contract,
    target_gene,
):
    payload = json.loads(output.dumps(target_gene))
    payload["root"]["source_details"] = {
        "label": "external",
        "tags": ["reviewed", "imported"],
    }

    restored = input_contract.loads(json.dumps(payload))

    assert getattr(restored, "source_details") == {
        "label": "external",
        "tags": ["reviewed", "imported"],
    }


def test_target_gene_output_rejects_the_wrong_value_type(output):
    with pytest.raises(TypeError, match="requires TargetGene"):
        output.dumps(cast(Any, "not-a-target-gene"))


def test_target_gene_output_schema_rejects_subclasses(output):
    class SpecializedTargetGene(TargetGene):
        pass

    target = SpecializedTargetGene(
        id="ENSG00000001",
        name="TARGET",
        chr="12",
        start=1,
        end=1,
        strand="+",
        sequence=Seq("A"),
        sites={},
    )

    with pytest.raises(ValueError, match=r"\$.root.__class__"):
        output.dumps(cast(Any, target))
