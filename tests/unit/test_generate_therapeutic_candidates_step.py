#!/usr/bin/env python
"""
Filename: tests/unit/test_generate_therapeutic_candidates_step.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Tests for GenerateTherapeuticCandidatesStep.
License: LGPL-3.0-or-later
"""

import json
import logging

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
from ASOkai._pipeline.steps.core.generate_therapeutic_candidates import (
    GenerateTherapeuticCandidatesStep,
)


def _write_target_gene(path, target) -> None:
    CreateTargetGeneStep.target_gene_output.write(path, target)


@pytest.fixture
def config(tmp_path):
    return {
        "datadir": str(tmp_path),
        "parameters": {
            "genome": {
                "assembly": "GRCh38",
                "release": 114,
                "source": "ensembl",
                "species": "Homo_sapiens",
            },
            "target": {"target_id": "ENSG00000133703", "k": 16, "region": "pre-mrna"},
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
        },
    }


@pytest.fixture
def step() -> GenerateTherapeuticCandidatesStep:
    return GenerateTherapeuticCandidatesStep()


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
    assert step.name == "generate-therapeutic-candidates"
    assert step.dependencies == ["create-target-gene"]
    assert (
        step.spec.input("target_gene").source is CreateTargetGeneStep.target_gene_output
    )
    assert isinstance(step.spec.input("target_gene"), FileInput)
    assert isinstance(GenerateTherapeuticCandidatesStep.target_gene_input.file_type, JsonFile)
    assert (
        GenerateTherapeuticCandidatesStep.target_gene_input.file_type.value_type is TargetGene
    )


def test_config_and_input_mapping(step):
    assert step.config_map == {
        "k": "parameters.target.k",
        "modality": "parameters.antisense.modality",
        "design": "parameters.antisense.design.type",
        "left_wing_length": "parameters.antisense.design.left_wing_length",
        "gap_length": "parameters.antisense.design.gap_length",
        "right_wing_length": "parameters.antisense.design.right_wing_length",
        "mechanism": "parameters.antisense.mechanism",
    }
    assert step.target_gene_input.configuration_path(step.name) == (
        "steps.generate-therapeutic-candidates.inputs.target_gene"
    )


def test_unscoped_k_follows_the_selected_target_gene(step, config, tmp_path):
    config["parameters"]["antisense"]["design"]["gap_length"] = 12
    producer_step = CreateTargetGeneStep()
    producer = StepRun(
        "gene",
        producer_step,
        config,
        parameters={"k": 18},
        inputs=tuple(
            StepInputBinding(file_input, tmp_path / file_input.name)
            for file_input in producer_step.spec.inputs
        ),
    )
    consumer = StepRun(
        "candidates",
        step,
        config,
        inputs=(
            StepInputBinding(
                step.target_gene_input,
                producer.output(CreateTargetGeneStep.target_gene_output),
            ),
        ),
    )

    assert config["parameters"]["target"]["k"] == 16
    assert consumer.parameters["k"] == 18
    assert "_k18_" in consumer.output_paths()["therapeutics"].name


def test_output_path_identifies_the_candidate_design(step, config, tmp_path):
    paths = _run(step, config, tmp_path).output_paths()
    assert paths["therapeutics"] == (
        tmp_path
        / "GRCh38"
        / "ensembl"
        / "114"
        / "targets"
        / "ENSG00000133703"
        / "antisense"
        / "ENSG00000133703_k16_pre-mrna_aso_gapmer_"
        "l3_g10_r3_rnase-h1_therapeutics.json"
    )
    assert paths["bindings"] == (
        tmp_path
        / "GRCh38"
        / "ensembl"
        / "114"
        / "targets"
        / "ENSG00000133703"
        / "antisense"
        / "ENSG00000133703_k16_pre-mrna_aso_gapmer_"
        "l3_g10_r3_rnase-h1_bindings.json"
    )


def test_output_path_uses_supplied_target_name(step, config, tmp_path):
    config["parameters"]["target"]["target_name"] = "KRAS"
    del config["parameters"]["target"]["target_id"]

    paths = _run(step, config, tmp_path).output_paths()

    assert paths["therapeutics"].name == (
        "KRAS_k16_pre-mrna_aso_gapmer_l3_g10_r3_" "rnase-h1_therapeutics.json"
    )
    assert paths["bindings"].name == (
        "KRAS_k16_pre-mrna_aso_gapmer_l3_g10_r3_rnase-h1_bindings.json"
    )
    assert paths["therapeutics"].parent.parent.name == "KRAS"


def test_output_path_supports_unmodified_asos(step, config, tmp_path):
    config["parameters"]["antisense"]["design"] = {"type": "unmodified"}

    paths = _run(step, config, tmp_path).output_paths()

    assert paths["therapeutics"].name == (
        "ENSG00000133703_k16_pre-mrna_aso_unmodified_"
        "lna_gna_rna_rnase-h1_therapeutics.json"
    )
    assert paths["bindings"].name == (
        "ENSG00000133703_k16_pre-mrna_aso_unmodified_"
        "lna_gna_rna_rnase-h1_bindings.json"
    )


def test_output_path_identifies_the_gapmer_layout(step, config, tmp_path):
    first = _run(step, config, tmp_path).output_paths()["therapeutics"]
    config["parameters"]["antisense"]["design"].update(
        {
            "left_wing_length": 4,
            "gap_length": 8,
            "right_wing_length": 4,
        }
    )
    second = _run(step, config, tmp_path).output_paths()["therapeutics"]

    assert first != second
    assert "l3_g10_r3" in first.name
    assert "l4_g8_r4" in second.name


def test_cwl_contains_scalar_configuration_and_file_io(step, config, tmp_path):
    run = _run(step, config, tmp_path)
    document = yaml.safe_load(StepCwlGenerator().render(run))

    assert document["baseCommand"] == [
        "ASOkai",
        "step",
        "--run-id",
        run.run_id,
        "generate-therapeutic-candidates",
    ]
    assert document["inputs"]["design"]["type"]["type"] == "enum"
    assert document["inputs"]["modality"]["type"]["type"] == "enum"
    assert document["inputs"]["mechanism"]["type"] == "string"
    assert document["inputs"]["left_wing_length"]["type"] == "int?"
    assert document["inputs"]["gap_length"]["type"] == "int?"
    assert document["inputs"]["right_wing_length"]["type"] == "int?"
    assert document["inputs"]["target_gene"]["type"] == "File"
    assert document["outputs"]["therapeutics"]["outputBinding"]["glob"] == (
        "ENSG00000133703_k16_pre-mrna_aso_gapmer_l3_g10_r3_rnase-h1_"
        "therapeutics.json"
    )
    assert document["outputs"]["bindings"]["outputBinding"]["glob"] == (
        "ENSG00000133703_k16_pre-mrna_aso_gapmer_l3_g10_r3_" "rnase-h1_bindings.json"
    )


def test_run_cli_writes_therapeutics_and_bindings_separately(tmp_path, caplog):
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

    caplog.set_level(logging.INFO)
    result = GenerateTherapeuticCandidatesStep().run_cli(
        [
            "--k",
            "16",
            "--modality",
            "aso",
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
    therapeutic = therapeutics["root"][0]
    binding = bindings["root"][0]
    assert result == 0
    assert therapeutic["id"].startswith("gapmer:l3g10r3-mrnase-h1-s16x")
    assert therapeutic["left_wing_length"] == 3
    assert therapeutic["gap_length"] == 10
    assert therapeutic["right_wing_length"] == 3
    assert binding["first_id"] == therapeutic["id"]
    assert binding["second_id"] == "ENSG00000133703-S00001"
    assert binding["first_sequence"] == therapeutic["sequence"]
    assert binding["structure"] == "(" * 16 + "&" + ")" * 16
    assert caplog.messages == [
        "Starting Step",
        "Generating gapmer candidates for 1 target sites",
        "Generated 1 therapeutics and 1 bindings",
        f"Writing therapeutics to {therapeutics_output}",
        f"Writing bindings to {bindings_output}",
        "Step Completed successfully",
    ]


def test_run_cli_shares_mechanism_across_sites_and_keeps_bindings(tmp_path):
    sites = [
        TranscriptSite(
            id=f"ENSG00000133703-S{number:05d}",
            loci=[TranscriptLocus(f"transcript-{number}", 0, 16)],
            sequence=Seq(sequence),
        )
        for number, sequence in enumerate(
            ("AAA" + "C" * 10 + "TTT", "CCC" + "A" * 10 + "GGG"),
            start=1,
        )
    ]
    target = TargetGene(
        id="ENSG00000133703",
        name="KRAS",
        chr="12",
        start=1,
        end=32,
        strand="+",
        sequence=sites[0].sequence + sites[1].sequence,
        sites={site.id: site for site in sites},
    )
    target_input = tmp_path / "target.json"
    _write_target_gene(target_input, target)
    therapeutics_output = tmp_path / "therapeutics.json"
    bindings_output = tmp_path / "bindings.json"

    result = GenerateTherapeuticCandidatesStep().run_cli(
        [
            "--k",
            "16",
            "--modality",
            "aso",
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

    therapeutic_document = json.loads(therapeutics_output.read_text())
    expected_bindings = [
        (item["id"], site.id) for item, site in zip(therapeutic_document["root"], sites)
    ]
    assert result == 0
    assert list(therapeutic_document["objects"]) == ["MechanismOfAction"]
    assert [item["mechanism"] for item in therapeutic_document["root"]] == [
        {"$ref": "#/objects/MechanismOfAction"}
    ] * 2
    assert [item["id"] for item in therapeutic_document["root"]] == [
        therapeutic_id for therapeutic_id, _ in expected_bindings
    ]

    therapeutics = GenerateTherapeuticCandidatesStep.therapeutics_output.file_type.read(
        therapeutics_output
    )
    bindings = GenerateTherapeuticCandidatesStep.bindings_output.file_type.read(bindings_output)
    assert therapeutics[0].mechanism is therapeutics[1].mechanism
    assert [
        (binding.first_id, binding.second_id) for binding in bindings
    ] == expected_bindings


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

    result = GenerateTherapeuticCandidatesStep().run_cli(
        [
            "--k",
            "4",
            "--modality",
            "aso",
            "--design",
            "unmodified",
            "--mechanism",
            "custom-mechanism",
            "--target-gene",
            str(target_input),
            "--therapeutics-output",
            str(therapeutics_output),
            "--bindings-output",
            str(bindings_output),
        ]
    )

    document = json.loads(therapeutics_output.read_text())
    therapeutic = document["root"][0]
    assert result == 0
    assert therapeutic["__class__"] == "ASO"
    assert therapeutic["id"] == "aso:mcustom-mechanism-s4x1b"
    restored = GenerateTherapeuticCandidatesStep.therapeutics_output.file_type.read(
        therapeutics_output
    )
    assert restored[0].mechanism.id == "custom-mechanism"
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

    result = GenerateTherapeuticCandidatesStep().run_cli(
        [
            "--k",
            "16",
            "--modality",
            "aso",
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
    assert json.loads(therapeutics_output.read_text()) == {
        "root": [],
        "objects": {},
    }
    assert json.loads(bindings_output.read_text()) == {
        "root": [],
        "objects": {},
    }


@pytest.mark.parametrize(
    ("design_arguments", "message"),
    [
        (
            ["--design", "gapmer"],
            "a gapmer design requires",
        ),
        (
            [
                "--design",
                "gapmer",
                "--left-wing-length",
                "0",
                "--gap-length",
                "10",
                "--right-wing-length",
                "6",
            ],
            "left_wing_length: 0 is less than the minimum of 1",
        ),
        (
            [
                "--design",
                "gapmer",
                "--left-wing-length",
                "3",
                "--gap-length",
                "8",
                "--right-wing-length",
                "3",
            ],
            "gapmer segment lengths must equal the target-site length",
        ),
        (
            [
                "--design",
                "unmodified",
                "--gap-length",
                "10",
            ],
            "an unmodified design must not define gapmer segment lengths",
        ),
    ],
)
def test_run_cli_rejects_invalid_design_layout_before_writing_outputs(
    design_arguments,
    message,
    tmp_path,
    capsys,
):
    target = TargetGene(
        id="ENSG00000133703",
        name="KRAS",
        chr="12",
        start=1,
        end=16,
        strand="+",
        sequence=Seq("A" * 16),
        sites={},
    )
    target_input = tmp_path / "target.json"
    _write_target_gene(target_input, target)
    output_dir = tmp_path / "outputs"

    with pytest.raises(SystemExit) as error:
        GenerateTherapeuticCandidatesStep().run_cli(
            [
                "--k",
                "16",
                "--modality",
                "aso",
                *design_arguments,
                "--mechanism",
                "rnase-h1",
                "--target-gene",
                str(target_input),
                "--therapeutics-output",
                str(output_dir / "therapeutics.json"),
                "--bindings-output",
                str(output_dir / "bindings.json"),
            ]
        )

    assert error.value.code == 2
    assert message in capsys.readouterr().err
    assert not output_dir.exists()


def test_run_cli_rejects_sirna_before_writing_output(tmp_path, capsys):
    target_input = tmp_path / "target.json"
    _write_target_gene(
        target_input,
        TargetGene(
            id="ENSG00000133703",
            name="KRAS",
            chr="12",
            start=1,
            end=16,
            strand="+",
            sequence=Seq("A" * 16),
            sites={},
        ),
    )
    with pytest.raises(SystemExit) as error:
        GenerateTherapeuticCandidatesStep().run_cli(
            [
                "--k",
                "16",
                "--modality",
                "sirna",
                "--design",
                "unmodified",
                "--mechanism",
                "risc",
                "--target-gene",
                str(target_input),
                "--therapeutics-output",
                str(tmp_path / "therapeutics.json"),
                "--bindings-output",
                str(tmp_path / "bindings.json"),
            ]
        )

    assert error.value.code == 2
    assert "siRNA candidate generation is not implemented" in capsys.readouterr().err
    assert not (tmp_path / "therapeutics.json").exists()


def test_sirna_validation_is_not_implemented(step):
    with pytest.raises(
        NotImplementedError,
        match="siRNA candidate generation is not implemented",
    ):
        step.validate_parameters({"modality": "sirna"})


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
        GenerateTherapeuticCandidatesStep().run_cli(
            [
                "--k",
                "16",
                "--modality",
                "aso",
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
