"""Tests for CreateTargetGeneStep."""
import pytest
from pathlib import Path
from pipeline.steps.create_target_gene import CreateTargetGeneStep
from pipeline.base import Step


@pytest.fixture
def config(tmp_path):
    return {
        "datadir": str(tmp_path),
        "genome": {
            "assembly_id": "GRCh38",
            "ensembl_release": 114,
            "species": "Homo_sapiens",
        },
        "target": {
            "target_id":   "ENSG00000133703",
            "target_name": "KRAS",
            "k":           16,
            "region":      "pre-mrna",
        },
    }


@pytest.fixture
def step():
    return CreateTargetGeneStep()


def test_implements_protocol(step):
    assert isinstance(step, Step)


def test_name(step):
    assert step.name == "create-target-gene"


def test_dependencies(step):
    assert "download-genome" in step.dependencies


def test_config_map_keys(step):
    assert "target_id"   in step.config_map
    assert "target_name" in step.config_map
    assert "k"           in step.config_map
    assert "region"      in step.config_map


def test_output_paths_structure(step, config, tmp_path):
    paths = step.output_paths(config)
    expected = tmp_path / "targets" / "gene" / "ENSG00000133703" / "GRCh38_ENSG00000133703.json"
    assert paths["target_gene"] == expected


def test_output_paths_uses_target_name_fallback(step, tmp_path):
    config = {
        "datadir": str(tmp_path),
        "genome": {"assembly_id": "GRCh38", "ensembl_release": 114, "species": "Homo_sapiens"},
        "target": {"target_name": "KRAS", "k": 16, "region": "pre-mrna"},
    }
    paths = step.output_paths(config)
    expected = tmp_path / "targets" / "gene" / "KRAS" / "GRCh38_KRAS.json"
    assert paths["target_gene"] == expected


def test_outdir(step, config, tmp_path):
    assert step.outdir(config) == tmp_path / "targets" / "gene" / "ENSG00000133703"


def test_outputs_do_not_exist(step, config):
    assert step.outputs_exist(config) is False


def test_outputs_exist(step, config, tmp_path):
    out = tmp_path / "targets" / "gene" / "ENSG00000133703"
    out.mkdir(parents=True)
    for p in step.output_paths(config).values():
        p.touch()
    assert step.outputs_exist(config) is True


def test_cleanup(step, config, tmp_path):
    out = tmp_path / "targets" / "gene" / "ENSG00000133703"
    out.mkdir(parents=True)
    for p in step.output_paths(config).values():
        p.touch()
    step.cleanup(config)
    assert step.outputs_exist(config) is False


def test_cwl_path_is_file(step):
    assert Path(step.cwl_path).exists(), f"CWL file not found: {step.cwl_path}"
