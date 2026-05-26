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
            "source": "ensembl",
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
    assert set(step.config_map.keys()) == {"assembly", "release", "source", "species"}


def test_source_from_config(step, config, tmp_path):
    assert step.outdir(config) == tmp_path / "GRCh38" / "genomes" / "ensembl" / "114"


def test_source_can_be_configured(step, config, tmp_path):
    config["genome"]["source"] = "ucsc"
    assert step.outdir(config) == tmp_path / "GRCh38" / "genomes" / "ucsc" / "114"


def test_output_paths_structure(step, config, tmp_path):
    paths = step.output_paths(config)
    base = tmp_path / "GRCh38" / "genomes" / "ensembl" / "114"
    assert paths["dna"] == base / "Homo_sapiens.GRCh38.dna.primary_assembly.fa.gz"
    assert paths["cdna"] == base / "Homo_sapiens.GRCh38.cdna.all.fa.gz"
    assert paths["annotation"] == base / "Homo_sapiens.GRCh38.114.gtf.gz"


def test_outdir(step, config, tmp_path):
    assert step.outdir(config) == tmp_path / "GRCh38" / "genomes" / "ensembl" / "114"


def test_outputs_do_not_exist(step, config):
    assert step.outputs_exist(config) is False


def test_outputs_exist(step, config, tmp_path):
    base = tmp_path / "GRCh38" / "genomes" / "ensembl" / "114"
    base.mkdir(parents=True)
    for p in step.output_paths(config).values():
        p.touch()
    assert step.outputs_exist(config) is True


def test_cleanup(step, config, tmp_path):
    base = tmp_path / "GRCh38" / "genomes" / "ensembl" / "114"
    base.mkdir(parents=True)
    for p in step.output_paths(config).values():
        p.touch()
    assert step.outputs_exist(config) is True
    step.cleanup(config)
    assert step.outputs_exist(config) is False


def test_cwl_path_is_file(step):
    assert Path(step.cwl_path).exists(), f"CWL file not found: {step.cwl_path}"


def test_main_downloads_with_mocked_ensembl_downloader(monkeypatch, tmp_path, capsys):
    from pipeline.steps import download_genome

    captured = {}

    class FakeDownloader:
        def __init__(self, **kwargs):
            captured["kwargs"] = kwargs

        def download(self, force):
            captured["force"] = force
            return {
                "dna": tmp_path / "dna.fa.gz",
                "cdna": tmp_path / "cdna.fa.gz",
                "annotation": tmp_path / "annotation.gtf.gz",
            }

    monkeypatch.setattr(download_genome, "EnsemblGenomeDownloader", FakeDownloader)

    result = download_genome.main(
        [
            "--assembly", "GRCh38",
            "--release", "114",
            "--source", "ensembl",
            "--species", "Homo_sapiens",
            "--outdir", str(tmp_path),
        ]
    )

    assert result == 0
    assert captured["kwargs"]["assembly_id"] == "GRCh38"
    assert captured["kwargs"]["ensembl_release"] == 114
    assert captured["kwargs"]["species"] == "homo_sapiens"
    assert captured["kwargs"]["genomes_root_dir"] == tmp_path
    assert captured["force"] is True
    assert "dna\t" in capsys.readouterr().out
