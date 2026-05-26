"""Tests for IntrinsicFeaturesStep."""
import pytest
from pathlib import Path
from pipeline.steps.intrinsic_features import IntrinsicFeaturesStep
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
    return IntrinsicFeaturesStep()


def test_implements_protocol(step):
    assert isinstance(step, Step)


def test_name(step):
    assert step.name == "intrinsic-features"


def test_dependencies(step):
    assert "create-target-gene" in step.dependencies


def test_config_map_keys(step):
    assert "target_id" in step.config_map
    assert "target_name" in step.config_map
    assert "k" in step.config_map
    assert "region" in step.config_map
    assert "assembly" in step.config_map


def test_output_paths_structure(step, config, tmp_path):
    paths = step.output_paths(config)
    expected = (
        tmp_path / "GRCh38" / "targets" / "ENSG00000133703"
        / "analysis" / "intrinsic" / "ENSG00000133703_k16_pre-mrna_intrinsic.json"
    )
    assert paths["intrinsic_features"] == expected


def test_output_paths_uses_target_name_fallback(step, tmp_path):
    config = {
        "datadir": str(tmp_path),
        "genome": {"assembly_id": "GRCh38", "ensembl_release": 114, "species": "Homo_sapiens"},
        "target": {"target_name": "KRAS", "k": 16, "region": "pre-mrna"},
    }
    paths = step.output_paths(config)
    expected = (
        tmp_path / "GRCh38" / "targets" / "KRAS"
        / "analysis" / "intrinsic" / "KRAS_k16_pre-mrna_intrinsic.json"
    )
    assert paths["intrinsic_features"] == expected


def test_outdir(step, config, tmp_path):
    assert step.outdir(config) == (
        tmp_path / "GRCh38" / "targets" / "ENSG00000133703" / "analysis" / "intrinsic"
    )


def test_outputs_do_not_exist(step, config):
    assert step.outputs_exist(config) is False


def test_outputs_exist(step, config, tmp_path):
    out = tmp_path / "GRCh38" / "targets" / "ENSG00000133703" / "analysis" / "intrinsic"
    out.mkdir(parents=True)
    for p in step.output_paths(config).values():
        p.touch()
    assert step.outputs_exist(config) is True


def test_cleanup(step, config, tmp_path):
    out = tmp_path / "GRCh38" / "targets" / "ENSG00000133703" / "analysis" / "intrinsic"
    out.mkdir(parents=True)
    for p in step.output_paths(config).values():
        p.touch()
    step.cleanup(config)
    assert step.outputs_exist(config) is False


def test_cwl_path_is_file(step):
    assert Path(step.cwl_path).exists(), f"CWL file not found: {step.cwl_path}"


def test_main_rejects_missing_target_identifier_before_analysis(tmp_path):
    from pipeline.steps import intrinsic_features

    with pytest.raises(SystemExit) as excinfo:
        intrinsic_features.main(
            [
                "--target-gene", str(tmp_path / "target.json"),
                "--assembly", "GRCh38",
                "--k", "16",
                "--region", "pre-mrna",
                "--output", str(tmp_path / "intrinsic.json"),
            ]
        )

    assert excinfo.value.code == 2
