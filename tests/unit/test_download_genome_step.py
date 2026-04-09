"""Tests for DownloadGenomeStep."""
import pytest
from pathlib import Path
from pipeline.steps.download_genome import DownloadGenomeStep
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
    }


@pytest.fixture
def step():
    return DownloadGenomeStep()


def test_implements_protocol(step):
    assert isinstance(step, Step)


def test_name(step):
    assert step.name == "download-genome"


def test_no_dependencies(step):
    assert step.dependencies == []


def test_config_map_keys(step):
    assert set(step.config_map.keys()) == {"assembly", "release", "species"}


def test_output_paths_structure(step, config, tmp_path):
    paths = step.output_paths(config)
    base = tmp_path / "genomes" / "ensembl" / "GRCh38" / "114"
    assert paths["dna"] == base / "Homo_sapiens.GRCh38.dna.primary_assembly.fa.gz"
    assert paths["cdna"] == base / "Homo_sapiens.GRCh38.cdna.all.fa.gz"
    assert paths["annotation"] == base / "Homo_sapiens.GRCh38.114.gtf.gz"


def test_outdir(step, config, tmp_path):
    assert step.outdir(config) == tmp_path / "genomes" / "ensembl" / "GRCh38" / "114"


def test_outputs_do_not_exist(step, config):
    assert step.outputs_exist(config) is False


def test_outputs_exist(step, config, tmp_path):
    base = tmp_path / "genomes" / "ensembl" / "GRCh38" / "114"
    base.mkdir(parents=True)
    for p in step.output_paths(config).values():
        p.touch()
    assert step.outputs_exist(config) is True


def test_cleanup(step, config, tmp_path):
    base = tmp_path / "genomes" / "ensembl" / "GRCh38" / "114"
    base.mkdir(parents=True)
    for p in step.output_paths(config).values():
        p.touch()
    assert step.outputs_exist(config) is True
    step.cleanup(config)
    assert step.outputs_exist(config) is False


def test_cwl_path_is_file(step):
    assert Path(step.cwl_path).exists(), f"CWL file not found: {step.cwl_path}"
