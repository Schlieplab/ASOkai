"""Tests for generated CWL workflows."""
import pytest
import yaml

from ASOkai._cwl.generation import generate_cwl
from ASOkai._pipeline.registry import get_steps


@pytest.fixture
def workflow_config(tmp_path):
    return {
        "datadir": str(tmp_path),
        "genome": {
            "assembly_id": "GRCh38",
            "ensembl_release": 114,
            "source": "ensembl",
            "species": "Homo_sapiens",
        },
        "target": {
            "target_id": "ENSG00000133703",
            "target_name": "KRAS",
            "k": 16,
            "region": "pre-mrna",
        },
    }


def test_generate_cwl_wires_download_outputs_into_create_target_gene(workflow_config):
    from ASOkai._pipeline.steps.create_target_gene import CreateTargetGeneStep
    from ASOkai._pipeline.steps.download_genome import DownloadGenomeStep

    doc = yaml.safe_load(
        generate_cwl(
            [DownloadGenomeStep(), CreateTargetGeneStep()],
            {},
            workflow_config,
        )
    )

    create_inputs = doc["steps"]["create_target_gene"]["in"]
    assert create_inputs["dna"] == "download_genome/dna"
    assert create_inputs["cdna"] == "download_genome/cdna"
    assert create_inputs["annotation"] == "download_genome/annotation"


def test_generate_cwl_does_not_pass_output_filenames_to_download_genome(workflow_config):
    from ASOkai._pipeline.steps.create_target_gene import CreateTargetGeneStep
    from ASOkai._pipeline.steps.download_genome import DownloadGenomeStep

    doc = yaml.safe_load(
        generate_cwl(
            [DownloadGenomeStep(), CreateTargetGeneStep()],
            {},
            workflow_config,
        )
    )

    download_inputs = doc["steps"]["download_genome"]["in"]
    assert "dna_output" not in download_inputs
    assert "cdna_output" not in download_inputs
    assert "annotation_output" not in download_inputs


def test_generate_cwl_uses_declared_step_input_types(workflow_config):
    from ASOkai._pipeline.steps.create_target_gene import CreateTargetGeneStep
    from ASOkai._pipeline.steps.download_genome import DownloadGenomeStep

    doc = yaml.safe_load(
        generate_cwl(
            [DownloadGenomeStep(), CreateTargetGeneStep()],
            {},
            workflow_config,
        )
    )

    assert doc["inputs"]["release"] == "int"
    assert doc["inputs"]["k"] == "int"
    assert doc["inputs"]["region"]["type"]["type"] == "enum"


def test_generate_cwl_pre_resolved_dependency_outputs_are_file_inputs(tmp_path):
    from ASOkai._pipeline.steps.create_target_gene import CreateTargetGeneStep

    config = {
        "datadir": str(tmp_path),
        "genome": {
            "assembly_id": "GRCh38",
            "ensembl_release": 114,
            "source": "ensembl",
            "species": "Homo_sapiens",
        },
        "target": {
            "target_id": "ENSG00000133703",
            "target_name": "KRAS",
            "k": 16,
            "region": "pre-mrna",
        },
    }

    doc = yaml.safe_load(
        generate_cwl(
            [CreateTargetGeneStep()],
            {"dna": tmp_path / "dna.fa.gz", "cdna": tmp_path / "cdna.fa.gz"},
            config,
        )
    )

    assert doc["inputs"]["dna"] == "File"
    assert doc["inputs"]["cdna"] == "File"
    assert doc["steps"]["create_target_gene"]["in"]["dna"] == "dna"
    assert doc["steps"]["create_target_gene"]["in"]["cdna"] == "cdna"


def test_generate_cwl_input_overrides_keep_declared_file_types_when_not_wired(workflow_config):
    from ASOkai._pipeline.steps.create_target_gene import CreateTargetGeneStep

    doc = yaml.safe_load(generate_cwl([CreateTargetGeneStep()], {}, workflow_config))

    assert doc["inputs"]["dna"] == "File"
    assert doc["inputs"]["cdna"] == "File"
    assert doc["inputs"]["annotation"] == "File"


def test_generate_cwl_outputs_come_from_final_step_only(workflow_config):
    from ASOkai._pipeline.steps.create_target_gene import CreateTargetGeneStep
    from ASOkai._pipeline.steps.download_genome import DownloadGenomeStep

    doc = yaml.safe_load(
        generate_cwl(
            [DownloadGenomeStep(), CreateTargetGeneStep()],
            {},
            workflow_config,
        )
    )

    assert list(doc["outputs"]) == ["target_gene"]
    assert doc["outputs"]["target_gene"]["outputSource"] == (
        "create_target_gene/target_gene"
    )


def test_generate_cwl_normalizes_step_ids_with_underscores(workflow_config):
    from ASOkai._pipeline.steps.create_target_gene import CreateTargetGeneStep
    from ASOkai._pipeline.steps.download_genome import DownloadGenomeStep

    doc = yaml.safe_load(
        generate_cwl(
            [DownloadGenomeStep(), CreateTargetGeneStep()],
            {},
            workflow_config,
        )
    )

    assert "download_genome" in doc["steps"]
    assert "create_target_gene" in doc["steps"]


def test_registered_step_output_paths_define_names(workflow_config):
    for step in get_steps().values():
        assert tuple(step.output_paths(workflow_config).keys())
