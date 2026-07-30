#!/usr/bin/env python
"""Tests for typed target-gene JSON inputs and outputs."""

from __future__ import annotations

import argparse
import json
from typing import Any, cast

from Bio.Seq import Seq
import pytest

from ASOkai.Sites import GenomicSite, TranscriptSite
from ASOkai.Targets import TargetGene
from ASOkai.plugin_api import FileInput, FileOutput, JsonFile
from ASOkai._pipeline.steps.core.create_target_gene import CreateTargetGeneStep
from ASOkai._pipeline.steps.core.generate_antisense_candidates import (
    GenerateAntisenseCandidatesStep,
)


@pytest.fixture
def output() -> FileOutput:
    return CreateTargetGeneStep.target_gene_output


@pytest.fixture
def input_contract() -> FileInput:
    return GenerateAntisenseCandidatesStep.target_gene_input


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
        transcript_id="ENST00000001",
        t_start=4,
        t_end=8,
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


def test_target_gene_roundtrip_uses_the_existing_serializable_shape(
    output,
    input_contract,
    target_gene,
):
    content = output.dumps(target_gene)
    payload = json.loads(content)

    assert payload["__class__"] == "TargetGene"
    assert payload["__module__"] == "ASOkai.Targets._target_gene"
    assert payload["sites"]["genomic-site"]["__class__"] == "GenomicSite"
    assert payload["sites"]["transcript-site"]["__class__"] == "TranscriptSite"
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
    input_contract,
    target_gene,
    tmp_path,
):
    path = tmp_path / "existing-target.json"
    target_gene.to_file(str(path))
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
    payload["__class__"] = "Other"

    with pytest.raises(ValueError, match=r"\$.__class__"):
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
    payload[field] = value

    with pytest.raises(ValueError, match=rf"\$.{field}"):
        input_contract.loads(json.dumps(payload))


def test_target_gene_schema_does_not_enforce_site_key_relationships(
    output,
    input_contract,
    target_gene,
):
    payload = json.loads(output.dumps(target_gene))
    payload["sites"]["wrong-key"] = payload["sites"].pop("genomic-site")

    restored = input_contract.loads(json.dumps(payload))

    assert restored.site_by_id("wrong-key").id == "genomic-site"


def test_target_gene_input_rejects_non_site_values(
    output,
    input_contract,
    target_gene,
):
    payload = json.loads(output.dumps(target_gene))
    payload["sites"]["not-a-site"] = 42

    with pytest.raises(ValueError, match=r"\$.sites.not-a-site"):
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
    destination = payload if site_id is None else payload["sites"][site_id]
    destination[field] = "not-a-genome"

    with pytest.raises(ValueError) as raised:
        input_contract.loads(json.dumps(payload))

    assert field in str(raised.value)


@pytest.mark.parametrize(
    ("site_id", "field", "value"),
    [
        ("genomic-site", "end", 5),
        ("transcript-site", "t_end", 9),
    ],
)
def test_target_gene_schema_does_not_enforce_coordinate_relationships(
    output,
    input_contract,
    target_gene,
    site_id,
    field,
    value,
):
    payload = json.loads(output.dumps(target_gene))
    payload["sites"][site_id][field] = value

    restored = input_contract.loads(json.dumps(payload))

    assert getattr(restored.site_by_id(site_id), field) == value


@pytest.mark.parametrize(
    "content",
    [
        '{"__class__": "TargetGene", "__class__": "Duplicate", '
        '"__module__": "ASOkai.Targets._target_gene"}',
        '{"__class__": "TargetGene", '
        '"__module__": "ASOkai.Targets._target_gene", "value": NaN}',
    ],
)
def test_target_gene_input_rejects_ambiguous_json(input_contract, content):
    with pytest.raises(ValueError, match="Invalid JSON"):
        input_contract.loads(content)


def test_target_gene_output_schema_does_not_enforce_site_key_relationships(
    output,
    target_gene,
):
    target_gene._sites["wrong-key"] = target_gene._sites.pop("genomic-site")

    content = output.dumps(target_gene)

    assert json.loads(content)["sites"]["wrong-key"]["id"] == "genomic-site"


def test_target_gene_schema_reports_all_structural_errors(
    output,
    input_contract,
    target_gene,
):
    payload = json.loads(output.dumps(target_gene))
    payload["name"] = []
    payload["start"] = True

    with pytest.raises(ValueError) as raised:
        input_contract.loads(json.dumps(payload))

    assert "$.name" in str(raised.value)
    assert "$.start" in str(raised.value)


def test_target_gene_input_allows_extra_scalar_kwargs(
    output,
    input_contract,
    target_gene,
):
    payload = json.loads(output.dumps(target_gene))
    payload["source_label"] = "external"
    payload["priority"] = 1

    restored = input_contract.loads(json.dumps(payload))

    assert restored.source_label == "external"
    assert restored.priority == 1


def test_target_gene_input_rejects_non_scalar_extra_kwargs(
    output,
    input_contract,
    target_gene,
):
    payload = json.loads(output.dumps(target_gene))
    payload["source_details"] = {"name": "external"}

    with pytest.raises(ValueError, match=r"\$.source_details"):
        input_contract.loads(json.dumps(payload))


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

    with pytest.raises(ValueError, match="does not match the TargetGene schema"):
        output.dumps(cast(Any, target))
