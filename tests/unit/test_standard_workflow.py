"""Tests for StandardWorkflow."""
import pytest
from pathlib import Path
from pipeline.workflows.standard import StandardWorkflow


@pytest.fixture
def config(tmp_path):
    return {
        "datadir": str(tmp_path),
        "genome": {
            "assembly_id":    "GRCh38",
            "ensembl_release": 114,
            "species":        "Homo_sapiens",
        },
        "target": {
            "target_id":   "ENSG00000133703",
            "target_name": "KRAS",
            "k":           16,
            "region":      "pre-mrna",
        },
    }


@pytest.fixture
def workflow():
    return StandardWorkflow()


def test_name(workflow):
    assert workflow.name == "standard"


def test_config_map_covers_all_inputs(workflow):
    keys = set(workflow.config_map.keys())
    assert {"assembly", "release", "species", "target_id", "target_name", "k", "region"} == keys


def test_output_paths(workflow, config, tmp_path):
    paths = workflow.output_paths(config)
    target_dir = tmp_path / "targets" / "gene" / "ENSG00000133703"
    analysis_dir = tmp_path / "analysis" / "intrinsic" / "ENSG00000133703"
    assert paths["target_gene"]        == target_dir / "GRCh38_ENSG00000133703.json"
    assert paths["intrinsic_features"] == analysis_dir / "GRCh38_ENSG00000133703_intrinsic.json"


def test_outputs_do_not_exist(workflow, config):
    assert workflow.outputs_exist(config) is False


def test_outputs_exist(workflow, config, tmp_path):
    (tmp_path / "targets" / "gene" / "ENSG00000133703").mkdir(parents=True)
    (tmp_path / "analysis" / "intrinsic" / "ENSG00000133703").mkdir(parents=True)
    for p in workflow.output_paths(config).values():
        p.touch()
    assert workflow.outputs_exist(config) is True


def test_cleanup(workflow, config, tmp_path):
    (tmp_path / "targets" / "gene" / "ENSG00000133703").mkdir(parents=True)
    (tmp_path / "analysis" / "intrinsic" / "ENSG00000133703").mkdir(parents=True)
    for p in workflow.output_paths(config).values():
        p.touch()
    workflow.cleanup(config)
    assert workflow.outputs_exist(config) is False


def test_cwl_path_is_file(workflow):
    assert Path(workflow.cwl_path).exists(), f"CWL file not found: {workflow.cwl_path}"
