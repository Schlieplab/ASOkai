#!/usr/bin/env python
"""Tests for GenerateAntisenseCandidatesStep."""

import json

from Bio.Seq import Seq
import pytest
import yaml

from ASOkai.Sites import TranscriptSite
from ASOkai._cwl.spec import StepCwlGenerator
from ASOkai._pipeline.base import CoreStep, Step
from ASOkai._pipeline.steps.generate_antisense_candidates import (
    GenerateAntisenseCandidatesStep,
)


@pytest.fixture
def config(tmp_path):
    return {
        "datadir": str(tmp_path),
        "genome": {"assembly_id": "GRCh38"},
        "target": {
            "target_id": "ENSG00000133703",
            "target_name": "KRAS",
            "k": 16,
            "region": "pre-mrna",
        },
        "antisense": {
            "modality": "aso",
            "mechanism": "rnase-h1",
            "chemistry": {"type": "gapmer", "layout": "3-10-3"},
        },
    }


@pytest.fixture
def step():
    return GenerateAntisenseCandidatesStep()


def test_step_contract_and_dependency(step):
    assert isinstance(step, Step)
    assert isinstance(step, CoreStep)
    assert step.name == "generate-antisense-candidates"
    assert step.dependencies == ["create-target-gene"]


def test_config_and_override_mapping(step):
    assert step.config_map == {
        "assembly": "genome.assembly_id",
        "target_id": "target.target_id",
        "target_name": "target.target_name",
        "k": "target.k",
        "region": "target.region",
        "modality": "antisense.modality",
        "chemistry": "antisense.chemistry.type",
        "layout": "antisense.chemistry.layout",
        "mechanism": "antisense.mechanism",
    }
    assert step.input_overrides == {"target_gene": "target.target_gene_path"}


def test_output_path_identifies_every_candidate_setting(step, config, tmp_path):
    paths = step.output_paths(config)
    assert paths["therapeutics"] == (
        tmp_path
        / "GRCh38"
        / "targets"
        / "ENSG00000133703"
        / "antisense"
        / "ENSG00000133703_k16_pre-mrna_aso_gapmer_3-10-3_rnase-h1_therapeutics.json"
    )
    assert paths["bindings"] == (
        tmp_path
        / "GRCh38"
        / "targets"
        / "ENSG00000133703"
        / "antisense"
        / "ENSG00000133703_k16_pre-mrna_aso_gapmer_3-10-3_rnase-h1_bindings.json"
    )


def test_output_path_uses_supplied_target_name(step, config, tmp_path):
    del config["target"]["target_id"]

    paths = step.output_paths(config)

    assert paths["therapeutics"].name == (
        "KRAS_k16_pre-mrna_aso_gapmer_3-10-3_rnase-h1_therapeutics.json"
    )
    assert paths["bindings"].name == (
        "KRAS_k16_pre-mrna_aso_gapmer_3-10-3_rnase-h1_bindings.json"
    )
    assert paths["therapeutics"].parent.parent.name == "KRAS"


def test_cwl_contains_scalar_configuration_and_file_io(step):
    document = yaml.safe_load(StepCwlGenerator().render(step))

    assert document["baseCommand"] == [
        "ASOkai",
        "step",
        "generate-antisense-candidates",
    ]
    assert document["inputs"]["modality"]["type"]["type"] == "enum"
    assert document["inputs"]["chemistry"]["type"]["type"] == "enum"
    assert document["inputs"]["mechanism"]["type"]["type"] == "enum"
    assert document["inputs"]["layout"]["type"] == "string"
    assert document["inputs"]["target_gene"]["type"] == "File"
    assert document["outputs"]["therapeutics"]["outputBinding"]["glob"] == (
        "therapeutics.json"
    )
    assert document["outputs"]["bindings"]["outputBinding"]["glob"] == "bindings.json"


def test_main_writes_therapeutics_and_bindings_separately(monkeypatch, tmp_path):
    from ASOkai.Targets import TargetGene
    from ASOkai._pipeline.steps import generate_antisense_candidates as command

    site = TranscriptSite(
        id="ENSG00000133703-S00001",
        transcript_id="transcript-1",
        t_start=0,
        t_end=16,
        sequence=Seq("AAA" + "C" * 10 + "TTT"),
    )
    target = TargetGene(
        id="ENSG00000133703",
        name="KRAS",
        chr="12",
        start=1,
        end=16,
        strand="+",
        sequence=Seq("AAA" + "C" * 10 + "TTT"),
        sites={site.id: site},
    )
    monkeypatch.setattr(
        TargetGene,
        "from_file",
        classmethod(lambda cls, path: target),
    )
    therapeutics_output = tmp_path / "nested" / "therapeutics.json"
    bindings_output = tmp_path / "nested" / "bindings.json"

    result = command.main(
        [
            "--assembly",
            "GRCh38",
            "--target-id",
            "ENSG00000133703",
            "--k",
            "16",
            "--region",
            "pre-mrna",
            "--modality",
            "aso",
            "--chemistry",
            "gapmer",
            "--layout",
            "3-10-3",
            "--mechanism",
            "rnase-h1",
            "--target-gene",
            str(tmp_path / "target.json"),
            "--therapeutics-output",
            str(therapeutics_output),
            "--bindings-output",
            str(bindings_output),
        ]
    )

    therapeutics = json.loads(therapeutics_output.read_text())
    bindings = json.loads(bindings_output.read_text())
    assert result == 0
    assert therapeutics[0]["id"] == (
        "ENSG00000133703-S00001-ASO-gapmer-3-10-3"
    )
    assert bindings[0]["therapeutic_id"] == therapeutics[0]["id"]
    assert bindings[0]["site_id"] == "ENSG00000133703-S00001"


def test_main_writes_empty_lists_for_target_without_sites(monkeypatch, tmp_path):
    from ASOkai.Targets import TargetGene
    from ASOkai._pipeline.steps import generate_antisense_candidates as command

    target = TargetGene(
        id="ENSG00000133703",
        name="KRAS",
        chr="12",
        start=1,
        end=16,
        strand="+",
        sequence=Seq("AAA" + "C" * 10 + "TTT"),
        sites={},
    )
    monkeypatch.setattr(
        TargetGene,
        "from_file",
        classmethod(lambda cls, path: target),
    )
    therapeutics_output = tmp_path / "therapeutics.json"
    bindings_output = tmp_path / "bindings.json"

    result = command.main(
        [
            "--assembly",
            "GRCh38",
            "--target-id",
            "ENSG00000133703",
            "--k",
            "16",
            "--region",
            "pre-mrna",
            "--modality",
            "aso",
            "--chemistry",
            "gapmer",
            "--layout",
            "3-10-3",
            "--mechanism",
            "rnase-h1",
            "--target-gene",
            str(tmp_path / "target.json"),
            "--therapeutics-output",
            str(therapeutics_output),
            "--bindings-output",
            str(bindings_output),
        ]
    )

    assert result == 0
    assert json.loads(therapeutics_output.read_text()) == []
    assert json.loads(bindings_output.read_text()) == []


def test_main_rejects_target_file_with_wrong_object_type(monkeypatch, tmp_path):
    from ASOkai.Targets import Target, TargetGene
    from ASOkai._pipeline.steps import generate_antisense_candidates as command

    monkeypatch.setattr(
        TargetGene,
        "from_file",
        classmethod(lambda cls, path: Target(id="not-a-target-gene")),
    )

    with pytest.raises(
        TypeError,
        match="The target gene file does not contain a TargetGene",
    ):
        command.main(
            [
                "--assembly",
                "GRCh38",
                "--target-id",
                "ENSG00000133703",
                "--k",
                "16",
                "--region",
                "pre-mrna",
                "--modality",
                "aso",
                "--chemistry",
                "gapmer",
                "--layout",
                "3-10-3",
                "--mechanism",
                "rnase-h1",
                "--target-gene",
                str(tmp_path / "target.json"),
                "--therapeutics-output",
                str(tmp_path / "therapeutics.json"),
                "--bindings-output",
                str(tmp_path / "bindings.json"),
            ]
        )


def test_main_rejects_missing_target_identifier(tmp_path):
    from ASOkai._pipeline.steps import generate_antisense_candidates as command

    with pytest.raises(SystemExit) as error:
        command.main(
            [
                "--assembly",
                "GRCh38",
                "--k",
                "16",
                "--region",
                "pre-mrna",
                "--modality",
                "aso",
                "--chemistry",
                "gapmer",
                "--layout",
                "3-10-3",
                "--mechanism",
                "rnase-h1",
                "--target-gene",
                str(tmp_path / "target.json"),
                "--therapeutics-output",
                str(tmp_path / "therapeutics.json"),
                "--bindings-output",
                str(tmp_path / "bindings.json"),
            ]
        )

    assert error.value.code == 2
