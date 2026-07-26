#!/usr/bin/env python
"""
Filename: tests/unit/test_download_genome_step.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Version: 0.1.1
Description: Tests for DownloadGenomeStep.
License: LGPL-3.0-or-later
"""

from pathlib import Path

import pytest
import yaml
from ASOkai._cwl.generation import StepCwlGenerator
from ASOkai.plugin_api import CoreStep, Step
from ASOkai._pipeline.steps.core.download_genome import DownloadGenomeStep


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
    assert isinstance(step, CoreStep)


def test_name(step):
    assert step.name == "download-genome"


def test_no_dependencies(step):
    assert step.dependencies == []


def test_config_map_keys(step):
    assert set(step.config_map.keys()) == {"assembly", "release", "source", "species"}


def test_source_from_config(step, config, tmp_path):
    assert step.output_paths(config)["dna"].parent == (
        tmp_path / "GRCh38" / "genomes" / "ensembl" / "114"
    )


def test_source_can_be_configured(step, config, tmp_path):
    config["genome"]["source"] = "ucsc"
    assert step.output_paths(config)["dna"].parent == (
        tmp_path / "GRCh38" / "genomes" / "ucsc" / "114"
    )


def test_output_paths_structure(step, config, tmp_path):
    paths = step.output_paths(config)
    base = tmp_path / "GRCh38" / "genomes" / "ensembl" / "114"
    assert paths["dna"] == base / "Homo_sapiens.GRCh38.dna.primary_assembly.fa.gz"
    assert paths["cdna"] == base / "Homo_sapiens.GRCh38.cdna.all.fa.gz"
    assert paths["annotation"] == base / "Homo_sapiens.GRCh38.114.gtf.gz"
    assert paths["db"] == base / "Homo_sapiens.GRCh38.114.gtf.db"


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


def test_cwl_spec_generates_command_line_tool(step, config):
    doc = yaml.safe_load(StepCwlGenerator().render(step, config))

    assert doc["class"] == "CommandLineTool"
    assert doc["baseCommand"] == ["ASOkai", "step", "download-genome"]
    assert doc["requirements"]["NetworkAccess"]["networkAccess"] is True
    assert "outdir" not in doc["inputs"]
    assert "dna_output" not in doc["inputs"]
    assert "InlineJavascriptRequirement" not in doc["requirements"]
    assert doc["inputs"]["release"]["type"] == "int"
    assert doc["inputs"]["source"]["default"] == "ensembl"
    assert "dna_filename" not in doc["inputs"]
    dna_filename = "Homo_sapiens.GRCh38.dna.primary_assembly.fa.gz"
    assert {
        "prefix": "--dna-output",
        "valueFrom": dna_filename,
    } in doc["arguments"]
    assert doc["outputs"]["dna"]["outputBinding"]["glob"] == dna_filename


def test_run_cli_downloads_with_mocked_ensembl_downloader(
    monkeypatch,
    tmp_path,
    capsys,
):
    from ASOkai._pipeline.steps.core import download_genome

    captured = {}

    class FakeDownloader:
        def __init__(self, **kwargs):
            captured["kwargs"] = kwargs

        def download(self, force, output_db=False):
            captured["force"] = force
            captured["output_db"] = output_db
            staging_dir = Path(captured["kwargs"]["genomes_root_dir"])
            for name in ("dna.fa.gz", "cdna.fa.gz", "annotation.gtf.gz", "annotation.db"):
                (staging_dir / name).write_text(name)
            return {
                "dna": staging_dir / "dna.fa.gz",
                "cdna": staging_dir / "cdna.fa.gz",
                "annotation": staging_dir / "annotation.gtf.gz",
                "db": staging_dir / "annotation.db",
            }

    monkeypatch.setattr(download_genome, "EnsemblGenomeDownloader", FakeDownloader)

    result = DownloadGenomeStep().run_cli(
        [
            "--assembly", "GRCh38",
            "--release", "114",
            "--source", "ensembl",
            "--species", "Homo_sapiens",
            "--dna-output", str(tmp_path / "out" / "dna.fa.gz"),
            "--cdna-output", str(tmp_path / "out" / "cdna.fa.gz"),
            "--annotation-output", str(tmp_path / "out" / "annotation.gtf.gz"),
            "--db-output", str(tmp_path / "out" / "annotation.db"),
        ]
    )

    assert result == 0
    assert captured["kwargs"]["assembly_id"] == "GRCh38"
    assert captured["kwargs"]["ensembl_release"] == 114
    assert captured["kwargs"]["species"] == "homo_sapiens"
    assert captured["kwargs"]["genomes_root_dir"] == (tmp_path / "out").resolve()
    assert captured["force"] is True
    assert captured["output_db"] is True
    assert (tmp_path / "out" / "dna.fa.gz").exists()
    assert (tmp_path / "out" / "cdna.fa.gz").exists()
    assert (tmp_path / "out" / "annotation.gtf.gz").exists()
    assert (tmp_path / "out" / "annotation.db").exists()
    assert "dna\t" in capsys.readouterr().out
