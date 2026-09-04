#!/usr/bin/env python
"""
Filename: tests/unit/test_download_genome_step.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Tests for DownloadGenomeStep.
License: LGPL-3.0-or-later
"""

from pathlib import Path

import pytest
import yaml
from ASOkai._cwl.generation import StepCwlGenerator
from ASOkai._pipeline.contracts.execution import StepRun
from ASOkai.Plugins import CoreStep, Step
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


@pytest.fixture
def run(step, config):
    return StepRun(step.name, step, config)


def test_step_contract(step):
    assert isinstance(step, Step)
    assert isinstance(step, CoreStep)
    assert step.name == "download-genome"
    assert step.dependencies == []
    assert set(step.config_map.keys()) == {"assembly", "release", "source", "species"}


def test_source_from_config(run, tmp_path):
    assert run.output_paths()["dna"].parent == (
        tmp_path / "GRCh38" / "ensembl" / "114" / "genome"
    )


def test_output_paths_structure(run, tmp_path):
    paths = run.output_paths()
    base = tmp_path / "GRCh38" / "ensembl" / "114" / "genome"
    assert paths["dna"] == base / "Homo_sapiens.GRCh38.dna.primary_assembly.fa.gz"
    assert paths["cdna"] == base / "Homo_sapiens.GRCh38.cdna.all.fa.gz"
    assert paths["annotation"] == base / "Homo_sapiens.GRCh38.114.gtf.gz"
    assert paths["db"] == base / "Homo_sapiens.GRCh38.114.gtf.db"


def test_cwl_spec_generates_command_line_tool(run):
    doc = yaml.safe_load(StepCwlGenerator().render(run))

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


def test_run_cli_downloads_to_declared_destinations(
    monkeypatch,
    tmp_path,
    caplog,
):
    from ASOkai._pipeline.steps.core import download_genome

    caplog.set_level("DEBUG")
    captured = {}

    class FakeDownloader:
        def __init__(self, **kwargs):
            captured["kwargs"] = kwargs

        def download(self, force, output_db=False):
            captured["force"] = force
            captured["output_db"] = output_db
            destinations = captured["kwargs"]["destinations"]
            for name, destination in destinations.items():
                destination.write_text(name)
            return destinations

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
    assert captured["kwargs"]["destinations"] == {
        "dna": tmp_path / "out" / "dna.fa.gz",
        "cdna": tmp_path / "out" / "cdna.fa.gz",
        "annotation": tmp_path / "out" / "annotation.gtf.gz",
        "db": tmp_path / "out" / "annotation.db",
    }
    assert captured["force"] is True
    assert captured["output_db"] is True
    assert (tmp_path / "out" / "dna.fa.gz").exists()
    assert (tmp_path / "out" / "cdna.fa.gz").exists()
    assert (tmp_path / "out" / "annotation.gtf.gz").exists()
    assert (tmp_path / "out" / "annotation.db").exists()
    assert "download-genome: wrote dna" in caplog.text
