#!/usr/bin/env python
"""
Filename: tests/unit/test_create_target_gene_step.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Tests for CreateTargetGeneStep.
License: LGPL-3.0-or-later
"""
import json

from Bio.Seq import Seq
import pytest
import yaml
from ASOkai.Targets import TargetGene
from ASOkai._cwl.generation import StepCwlGenerator
from ASOkai.Plugins import CoreStep, FileOutput, JsonFile, Step
from ASOkai._pipeline.contracts.execution import StepInputBinding, StepRun
from ASOkai._pipeline.steps.core.create_target_gene import CreateTargetGeneStep
from ASOkai._pipeline.steps.core.download_genome import DownloadGenomeStep


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
            "k":           16,
            "region":      "pre-mrna",
        },
    }


@pytest.fixture
def step():
    return CreateTargetGeneStep()


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


def test_step_contract(step):
    assert isinstance(step, Step)
    assert isinstance(step, CoreStep)
    assert step.name == "create-target-gene"
    assert step.dependencies == ["download-genome"]
    assert step.spec.input("dna").source is DownloadGenomeStep.dna_output
    assert set(step.config_map) >= {"target_id", "target_name", "k", "region"}
    assert "release" not in step.config_map


def test_output_paths_structure(step, config, tmp_path):
    paths = _run(step, config, tmp_path).output_paths()
    expected = (
        tmp_path
        / "GRCh38"
        / "genomes"
        / "ensembl"
        / "114"
        / "Homo_sapiens"
        / "targets"
        / "ENSG00000133703"
        / "ENSG00000133703_k16_pre-mrna.json"
    )
    assert paths["target_gene"] == expected


def test_output_paths_uses_target_name_fallback(step, tmp_path):
    config = {
        "datadir": str(tmp_path),
        "genome": {"assembly_id": "GRCh38", "ensembl_release": 114, "species": "Homo_sapiens"},
        "target": {"target_name": "KRAS", "k": 16, "region": "pre-mrna"},
    }
    paths = _run(step, config, tmp_path).output_paths()
    expected = (
        tmp_path
        / "GRCh38"
        / "genomes"
        / "ensembl"
        / "114"
        / "Homo_sapiens"
        / "targets"
        / "KRAS"
        / "KRAS_k16_pre-mrna.json"
    )
    assert paths["target_gene"] == expected


def test_output_path_identifies_the_genome_release(step, config, tmp_path):
    first = _run(step, config, tmp_path).output_paths()["target_gene"]
    config["genome"]["ensembl_release"] = 115
    second = _run(step, config, tmp_path).output_paths()["target_gene"]

    assert first != second
    assert first.parts[-6:-3] == ("ensembl", "114", "Homo_sapiens")
    assert second.parts[-6:-3] == ("ensembl", "115", "Homo_sapiens")


def test_cwl_spec_generates_command_line_tool(step, config, tmp_path):
    run = _run(step, config, tmp_path)
    doc = yaml.safe_load(StepCwlGenerator().render(run))
    output = step.spec.output("target_gene")

    assert isinstance(output, FileOutput)
    assert isinstance(output.file_type, JsonFile)
    assert output.file_type.value_type is TargetGene
    assert doc["class"] == "CommandLineTool"
    assert doc["baseCommand"] == ["ASOkai", "step", "create-target-gene"]
    assert doc["inputs"]["k"]["type"] == "int"
    assert doc["inputs"]["region"]["type"]["type"] == "enum"
    assert "target_gene_output" not in doc["inputs"]
    assert "target_gene_filename" not in doc["inputs"]
    assert {
        "prefix": "--target-gene-output",
        "valueFrom": "ENSG00000133703_k16_pre-mrna.json",
    } in doc["arguments"]
    assert doc["outputs"]["target_gene"]["outputBinding"]["glob"] == (
        "ENSG00000133703_k16_pre-mrna.json"
    )


def test_run_cli_accepts_target_name_only_with_mocked_genome_creation(
    monkeypatch,
    tmp_path,
):
    import ASOkai.Targets as targets_mod
    import GenomeUtils.Genome as genome_mod

    output = tmp_path / "out" / "target.json"
    captured = {}

    class FakeGenomeBuilder:
        def __init__(self, **kwargs):
            captured["builder_kwargs"] = kwargs

        def with_dna_fasta(self, path):
            captured["dna"] = path
            return self

        def with_cdna_fasta(self, path):
            captured["cdna"] = path
            return self

        def with_gtf_file(self, path, db_path=None):
            captured["annotation"] = path
            captured["db"] = db_path
            return self

        def build(self):
            return "genome", None

    target_gene = TargetGene(
        id="ENSG00000133703",
        name="KRAS",
        chr="12",
        start=1,
        end=4,
        strand="+",
        sequence=Seq("ACGT"),
        sites={},
    )

    def fake_create_target_gene(genome, **kwargs):
        captured["genome"] = genome
        captured["creator_kwargs"] = kwargs
        return target_gene

    monkeypatch.setattr(genome_mod, "GenomeBuilder", FakeGenomeBuilder)
    monkeypatch.setattr(targets_mod, "create_target_gene", fake_create_target_gene)

    result = CreateTargetGeneStep().run_cli(
        [
            "--target-name", "KRAS",
            "--k", "16",
            "--region", "pre-mrna",
            "--dna", str(tmp_path / "dna.fa.gz"),
            "--cdna", str(tmp_path / "cdna.fa.gz"),
            "--annotation", str(tmp_path / "annotation.gtf.gz"),
            "--db", str(tmp_path / "annotation.gtf.db"),
            "--assembly", "GRCh38",
            "--species", "Homo_sapiens",
            "--target-gene-output", str(output),
        ]
    )

    assert result == 0
    assert output.exists()
    payload = json.loads(output.read_text())
    assert payload["__class__"] == "TargetGene"
    assert payload["__module__"] == "ASOkai.Targets._target_gene"
    assert payload["id"] == "ENSG00000133703"
    assert payload["name"] == "KRAS"
    assert payload["chr"] == "12"
    assert payload["start"] == 1
    assert payload["end"] == 4
    assert payload["strand"] == "+"
    assert payload["sequence"] == "ACGT"
    assert payload["sites"] == {}
    assert captured["builder_kwargs"]["species"] == "Homo sapiens"
    assert captured["db"] == tmp_path / "annotation.gtf.db"
    assert captured["creator_kwargs"]["target_id"] is None
    assert captured["creator_kwargs"]["target_name"] == "KRAS"
    assert captured["creator_kwargs"]["site_length"] == 16


@pytest.mark.parametrize(
    "target_arguments",
    [
        [],
        [
            "--target-id",
            "ENSG00000133703",
            "--target-name",
            "KRAS",
        ],
    ],
)
def test_run_cli_rejects_invalid_target_selection_before_loading_genome(
    target_arguments,
    tmp_path,
    capsys,
):
    output = tmp_path / "out" / "target.json"
    arguments = [
        *target_arguments,
        "--k",
        "16",
        "--region",
        "pre-mrna",
        "--dna",
        str(tmp_path / "dna.fa.gz"),
        "--cdna",
        str(tmp_path / "cdna.fa.gz"),
        "--annotation",
        str(tmp_path / "annotation.gtf.gz"),
        "--db",
        str(tmp_path / "annotation.gtf.db"),
        "--assembly",
        "GRCh38",
        "--species",
        "Homo_sapiens",
        "--target-gene-output",
        str(output),
    ]

    with pytest.raises(SystemExit) as error:
        CreateTargetGeneStep().run_cli(arguments)

    assert error.value.code == 2
    assert "exactly one of --target-id or --target-name" in capsys.readouterr().err
    assert not output.parent.exists()
