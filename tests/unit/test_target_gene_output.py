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
def output() -> FileOutput[TargetGene]:
    return CreateTargetGeneStep.target_gene_output


@pytest.fixture
def input_contract() -> FileInput[TargetGene]:
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

    with pytest.raises(ValueError, match="must contain .*TargetGene"):
        input_contract.loads(json.dumps(payload))


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("name", "", "name must be a non-blank string"),
        ("start", True, "start must be an integer greater than zero"),
        ("strand", "?", "strand must be"),
        ("sequence", "", "sequence must be non-empty"),
    ],
)
def test_target_gene_input_rejects_invalid_core_fields(
    output,
    input_contract,
    target_gene,
    field,
    value,
    message,
):
    payload = json.loads(output.dumps(target_gene))
    payload[field] = value

    with pytest.raises(ValueError, match=message):
        input_contract.loads(json.dumps(payload))


def test_target_gene_input_rejects_site_key_mismatch(
    output,
    input_contract,
    target_gene,
):
    payload = json.loads(output.dumps(target_gene))
    payload["sites"]["wrong-key"] = payload["sites"].pop("genomic-site")

    with pytest.raises(ValueError, match="does not match site id"):
        input_contract.loads(json.dumps(payload))


def test_target_gene_input_rejects_non_site_values(
    output,
    input_contract,
    target_gene,
):
    payload = json.loads(output.dumps(target_gene))
    payload["sites"]["not-a-site"] = 42

    with pytest.raises(ValueError, match="must contain a Site instance"):
        input_contract.loads(json.dumps(payload))


@pytest.mark.parametrize(
    ("site_id", "field", "message"),
    [
        (None, "genome", "genome must be a Genome or None"),
        (
            None,
            "chromosome",
            "chromosome reference must be a Chromosome or None",
        ),
        ("genomic-site", "genome", "genome must be a Genome or None"),
    ],
)
def test_target_gene_input_rejects_invalid_runtime_references(
    output,
    input_contract,
    target_gene,
    site_id,
    field,
    message,
):
    payload = json.loads(output.dumps(target_gene))
    destination = payload if site_id is None else payload["sites"][site_id]
    destination[field] = "not-a-genome"

    with pytest.raises(ValueError, match=message):
        input_contract.loads(json.dumps(payload))


@pytest.mark.parametrize(
    ("site_id", "field", "value", "message"),
    [
        (
            "genomic-site",
            "end",
            5,
            "sequence length must match its inclusive interval",
        ),
        (
            "transcript-site",
            "t_end",
            9,
            "sequence length must match its half-open interval",
        ),
    ],
)
def test_target_gene_input_rejects_invalid_site_intervals(
    output,
    input_contract,
    target_gene,
    site_id,
    field,
    value,
    message,
):
    payload = json.loads(output.dumps(target_gene))
    payload["sites"][site_id][field] = value

    with pytest.raises(ValueError, match=message):
        input_contract.loads(json.dumps(payload))


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


def test_target_gene_output_rejects_invalid_objects(output, target_gene):
    target_gene._sites["wrong-key"] = target_gene._sites.pop("genomic-site")

    with pytest.raises(ValueError, match="does not match site id"):
        output.dumps(target_gene)


def test_target_gene_output_rejects_the_wrong_value_type(output):
    with pytest.raises(TypeError, match="requires TargetGene"):
        output.dumps(cast(Any, "not-a-target-gene"))


def test_target_gene_output_rejects_subclasses(output):
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

    with pytest.raises(TypeError, match="requires TargetGene"):
        output.dumps(cast(Any, target))
