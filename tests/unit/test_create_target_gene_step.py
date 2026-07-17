#!/usr/bin/env python
"""Tests for CreateTargetGeneStep."""
import pytest
from pathlib import Path
import yaml
from ASOkai._cwl.spec import StepCwlGenerator
from ASOkai._pipeline.steps.create_target_gene import CreateTargetGeneStep
from ASOkai._pipeline.base import CoreStep, Step


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
    assert isinstance(step, CoreStep)


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
    expected = tmp_path / "GRCh38" / "targets" / "ENSG00000133703" / "ENSG00000133703_k16_pre-mrna.json"
    assert paths["target_gene"] == expected


def test_output_paths_uses_target_name_fallback(step, tmp_path):
    config = {
        "datadir": str(tmp_path),
        "genome": {"assembly_id": "GRCh38", "ensembl_release": 114, "species": "Homo_sapiens"},
        "target": {"target_name": "KRAS", "k": 16, "region": "pre-mrna"},
    }
    paths = step.output_paths(config)
    expected = tmp_path / "GRCh38" / "targets" / "KRAS" / "KRAS_k16_pre-mrna.json"
    assert paths["target_gene"] == expected


def test_outputs_do_not_exist(step, config):
    assert step.outputs_exist(config) is False


def test_outputs_exist(step, config, tmp_path):
    out = tmp_path / "GRCh38" / "targets" / "ENSG00000133703"
    out.mkdir(parents=True)
    for p in step.output_paths(config).values():
        p.touch()
    assert step.outputs_exist(config) is True


def test_cleanup(step, config, tmp_path):
    out = tmp_path / "GRCh38" / "targets" / "ENSG00000133703"
    out.mkdir(parents=True)
    for p in step.output_paths(config).values():
        p.touch()
    step.cleanup(config)
    assert step.outputs_exist(config) is False


def test_cwl_spec_generates_command_line_tool(step):
    doc = yaml.safe_load(StepCwlGenerator().render(step))

    assert doc["class"] == "CommandLineTool"
    assert doc["baseCommand"] == ["ASOkai", "step", "create-target-gene"]
    assert doc["inputs"]["k"]["type"] == "int"
    assert doc["inputs"]["region"]["type"]["type"] == "enum"
    assert "target_gene_output" not in doc["inputs"]
    assert "target_gene_filename" not in doc["inputs"]
    assert {
        "prefix": "--target-gene-output",
        "valueFrom": "target_gene.json",
    } in doc["arguments"]
    assert doc["outputs"]["target_gene"]["outputBinding"]["glob"] == (
        "target_gene.json"
    )


def test_main_rejects_missing_target_identifier(tmp_path):
    from ASOkai._pipeline.steps import create_target_gene

    with pytest.raises(SystemExit) as excinfo:
        create_target_gene.main(
            [
                "--k", "16",
                "--region", "pre-mrna",
                "--dna", str(tmp_path / "dna.fa.gz"),
                "--cdna", str(tmp_path / "cdna.fa.gz"),
                "--annotation", str(tmp_path / "annotation.gtf.gz"),
                "--db", str(tmp_path / "annotation.gtf.db"),
                "--assembly", "GRCh38",
                "--release", "114",
                "--species", "Homo_sapiens",
                "--target-gene-output", str(tmp_path / "target.json"),
            ]
        )

    assert excinfo.value.code == 2


def test_main_accepts_target_name_only_with_mocked_genome_creation(monkeypatch, tmp_path):
    from ASOkai._pipeline.steps import create_target_gene
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

    class FakeTargetGene:
        def to_file(self, path):
            captured["output"] = path
            Path(path).write_text("{}")

    class FakeTargetGeneCreator:
        @classmethod
        def from_genome(cls, genome, **kwargs):
            captured["genome"] = genome
            captured["creator_kwargs"] = kwargs
            return FakeTargetGene()

    monkeypatch.setattr(genome_mod, "GenomeBuilder", FakeGenomeBuilder)
    monkeypatch.setattr(targets_mod, "TargetGeneCreator", FakeTargetGeneCreator)

    result = create_target_gene.main(
        [
            "--target-name", "KRAS",
            "--k", "16",
            "--region", "pre-mrna",
            "--dna", str(tmp_path / "dna.fa.gz"),
            "--cdna", str(tmp_path / "cdna.fa.gz"),
            "--annotation", str(tmp_path / "annotation.gtf.gz"),
            "--db", str(tmp_path / "annotation.gtf.db"),
            "--assembly", "GRCh38",
            "--release", "114",
            "--species", "Homo_sapiens",
            "--target-gene-output", str(output),
        ]
    )

    assert result == 0
    assert output.exists()
    assert captured["builder_kwargs"]["species"] == "Homo sapiens"
    assert captured["db"] == tmp_path / "annotation.gtf.db"
    assert captured["creator_kwargs"]["target_id"] is None
    assert captured["creator_kwargs"]["target_name"] == "KRAS"
    assert captured["creator_kwargs"]["k"] == 16
