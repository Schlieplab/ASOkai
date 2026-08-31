#!/usr/bin/env python
"""Tests for GenerateASOCandidatesStep."""

import json

from Bio.Seq import Seq
from GenomeUtils.Genome import TranscriptLocus
import pytest
import yaml

from ASOkai.Sites import TranscriptSite
from ASOkai.Targets import TargetGene
from ASOkai._cwl.generation import StepCwlGenerator
from ASOkai.Plugins import CoreStep, FileInput, JsonFile, Step
from ASOkai._pipeline.contracts.execution import StepInputBinding, StepRun
from ASOkai._pipeline.steps.core.create_target_gene import CreateTargetGeneStep
from ASOkai._pipeline.steps.core.generate_aso_candidates import (
    GenerateASOCandidatesStep,
)


def _write_target_gene(path, target) -> None:
    CreateTargetGeneStep.target_gene_output.write(path, target)


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
            "design": {
                "type": "gapmer",
                "left_wing_length": 3,
                "gap_length": 10,
                "right_wing_length": 3,
            },
        },
    }


@pytest.fixture
def step() -> GenerateASOCandidatesStep:
    return GenerateASOCandidatesStep()


def _run(step, config, tmp_path):
    return StepRun(
        step.name,
        step,
        config,
        inputs=tuple(
            StepInputBinding(file_input, tmp_path / file_input.name)
            for file_input in step.spec.inputs
        ),
    )


def test_step_contract_and_dependency(step):
    assert isinstance(step, Step)
    assert isinstance(step, CoreStep)
    assert step.name == "generate-aso-candidates"
    assert step.dependencies == ["create-target-gene"]
    assert (
        step.spec.input("target_gene").source
        is CreateTargetGeneStep.target_gene_output
    )
    assert isinstance(step.spec.input("target_gene"), FileInput)
    assert isinstance(GenerateASOCandidatesStep.target_gene_input.file_type, JsonFile)
    assert (
        GenerateASOCandidatesStep.target_gene_input.file_type.value_type
        is TargetGene
    )


def test_config_and_input_mapping(step):
    assert step.config_map == {
        "assembly": "genome.assembly_id",
        "target_id": "target.target_id",
        "target_name": "target.target_name",
        "k": "target.k",
        "region": "target.region",
        "design": "antisense.design.type",
        "left_wing_length": "antisense.design.left_wing_length",
        "gap_length": "antisense.design.gap_length",
        "right_wing_length": "antisense.design.right_wing_length",
        "mechanism": "antisense.mechanism",
    }
    assert step.target_gene_input.configuration_path(step.name) == (
        "steps.generate-aso-candidates.inputs.target_gene"
    )


def test_output_path_identifies_the_candidate_design(step, config, tmp_path):
    paths = _run(step, config, tmp_path).output_paths()
    assert paths["therapeutics"] == (
        tmp_path
        / "GRCh38"
        / "targets"
        / "ENSG00000133703"
        / "antisense"
        / "ENSG00000133703_k16_pre-mrna_aso_gapmer_rnase-h1_therapeutics.json"
    )
    assert paths["bindings"] == (
        tmp_path
        / "GRCh38"
        / "targets"
        / "ENSG00000133703"
        / "antisense"
        / "ENSG00000133703_k16_pre-mrna_aso_gapmer_rnase-h1_bindings.json"
    )


def test_output_path_uses_supplied_target_name(step, config, tmp_path):
    del config["target"]["target_id"]

    paths = _run(step, config, tmp_path).output_paths()

    assert paths["therapeutics"].name == (
        "KRAS_k16_pre-mrna_aso_gapmer_rnase-h1_therapeutics.json"
    )
    assert paths["bindings"].name == (
        "KRAS_k16_pre-mrna_aso_gapmer_rnase-h1_bindings.json"
    )
    assert paths["therapeutics"].parent.parent.name == "KRAS"


def test_output_path_supports_unmodified_asos(step, config, tmp_path):
    config["antisense"]["design"] = {"type": "unmodified"}

    paths = _run(step, config, tmp_path).output_paths()

    assert paths["therapeutics"].name == (
        "ENSG00000133703_k16_pre-mrna_aso_unmodified_"
        "rnase-h1_therapeutics.json"
    )
    assert paths["bindings"].name == (
        "ENSG00000133703_k16_pre-mrna_aso_unmodified_"
        "rnase-h1_bindings.json"
    )


def test_cwl_contains_scalar_configuration_and_file_io(step, config, tmp_path):
    run = _run(step, config, tmp_path)
    document = yaml.safe_load(StepCwlGenerator().render(run))

    assert document["baseCommand"] == [
        "ASOkai",
        "step",
        "generate-aso-candidates",
    ]
    assert document["inputs"]["design"]["type"]["type"] == "enum"
    assert document["inputs"]["mechanism"]["type"]["type"] == "enum"
    assert document["inputs"]["left_wing_length"]["type"] == "int?"
    assert document["inputs"]["gap_length"]["type"] == "int?"
    assert document["inputs"]["right_wing_length"]["type"] == "int?"
    assert document["inputs"]["target_gene"]["type"] == "File"
    assert document["outputs"]["therapeutics"]["outputBinding"]["glob"] == (
        "ENSG00000133703_k16_pre-mrna_aso_gapmer_rnase-h1_"
        "therapeutics.json"
    )
    assert document["outputs"]["bindings"]["outputBinding"]["glob"] == (
        "ENSG00000133703_k16_pre-mrna_aso_gapmer_rnase-h1_bindings.json"
    )


def test_run_cli_writes_therapeutics_and_bindings_separately(tmp_path):
    from ASOkai.Targets import TargetGene

    site = TranscriptSite(
        id="ENSG00000133703-S00001",
        loci=[TranscriptLocus("transcript-1", 0, 16)],
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
    target_input = tmp_path / "target.json"
    _write_target_gene(target_input, target)
    therapeutics_output = tmp_path / "nested" / "therapeutics.json"
    bindings_output = tmp_path / "nested" / "bindings.json"

    result = GenerateASOCandidatesStep().run_cli(
        [
            "--assembly",
            "GRCh38",
            "--target-id",
            "ENSG00000133703",
            "--k",
            "16",
            "--region",
            "pre-mrna",
            "--design",
            "gapmer",
            "--left-wing-length",
            "3",
            "--gap-length",
            "10",
            "--right-wing-length",
            "3",
            "--mechanism",
            "rnase-h1",
            "--target-gene",
            str(target_input),
            "--therapeutics-output",
            str(therapeutics_output),
            "--bindings-output",
            str(bindings_output),
        ]
    )

    therapeutics = json.loads(therapeutics_output.read_text())
    bindings = json.loads(bindings_output.read_text())
    assert result == 0
    assert therapeutics[0]["id"] == "ENSG00000133703-S00001-Gapmer"
    assert therapeutics[0]["left_wing_length"] == 3
    assert therapeutics[0]["gap_length"] == 10
    assert therapeutics[0]["right_wing_length"] == 3
    assert bindings[0]["therapeutic_id"] == therapeutics[0]["id"]
    assert bindings[0]["site_id"] == "ENSG00000133703-S00001"


def test_run_cli_generates_unmodified_asos_without_gapmer_lengths(tmp_path):
    site = TranscriptSite(
        id="ENSG00000133703-S00001",
        loci=[TranscriptLocus("transcript-1", 0, 4)],
        sequence=Seq("ACGT"),
    )
    target = TargetGene(
        id="ENSG00000133703",
        name="KRAS",
        chr="12",
        start=1,
        end=4,
        strand="+",
        sequence=Seq("ACGT"),
        sites={site.id: site},
    )
    target_input = tmp_path / "target.json"
    _write_target_gene(target_input, target)
    therapeutics_output = tmp_path / "therapeutics.json"
    bindings_output = tmp_path / "bindings.json"

    result = GenerateASOCandidatesStep().run_cli(
        [
            "--assembly",
            "GRCh38",
            "--target-id",
            "ENSG00000133703",
            "--k",
            "4",
            "--region",
            "pre-mrna",
            "--design",
            "unmodified",
            "--mechanism",
            "rnase-h1",
            "--target-gene",
            str(target_input),
            "--therapeutics-output",
            str(therapeutics_output),
            "--bindings-output",
            str(bindings_output),
        ]
    )

    therapeutic = json.loads(therapeutics_output.read_text())[0]
    assert result == 0
    assert therapeutic["__class__"] == "ASO"
    assert therapeutic["id"] == "ENSG00000133703-S00001-ASO"
    assert "left_wing_length" not in therapeutic
    assert "gap_length" not in therapeutic
    assert "right_wing_length" not in therapeutic


def test_run_cli_writes_empty_lists_for_target_without_sites(tmp_path):
    from ASOkai.Targets import TargetGene

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
    target_input = tmp_path / "target.json"
    _write_target_gene(target_input, target)
    therapeutics_output = tmp_path / "therapeutics.json"
    bindings_output = tmp_path / "bindings.json"

    result = GenerateASOCandidatesStep().run_cli(
        [
            "--assembly",
            "GRCh38",
            "--target-id",
            "ENSG00000133703",
            "--k",
            "16",
            "--region",
            "pre-mrna",
            "--design",
            "unmodified",
            "--mechanism",
            "rnase-h1",
            "--target-gene",
            str(target_input),
            "--therapeutics-output",
            str(therapeutics_output),
            "--bindings-output",
            str(bindings_output),
        ]
    )

    assert result == 0
    assert json.loads(therapeutics_output.read_text()) == []
    assert json.loads(bindings_output.read_text()) == []


def test_run_cli_rejects_target_file_with_wrong_type(tmp_path, capsys):
    target_input = tmp_path / "target.json"
    target_input.write_text(
        json.dumps(
            {
                "__class__": "Other",
                "__module__": "some.other.module",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(SystemExit) as error:
        GenerateASOCandidatesStep().run_cli(
            [
                "--assembly",
                "GRCh38",
                "--target-id",
                "ENSG00000133703",
                "--k",
                "16",
                "--region",
                "pre-mrna",
                "--design",
                "unmodified",
                "--mechanism",
                "rnase-h1",
                "--target-gene",
                str(target_input),
                "--therapeutics-output",
                str(tmp_path / "therapeutics.json"),
                "--bindings-output",
                str(tmp_path / "bindings.json"),
            ]
    )
    assert error.value.code == 2
    assert "does not match the TargetGene schema" in capsys.readouterr().err
