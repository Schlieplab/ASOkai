#!/usr/bin/env python
"""
Filename: tests/unit/test_intrinsic_features_step.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Tests for IntrinsicFeaturesStep.
License: LGPL-3.0-or-later
"""

from Bio.Seq import Seq
from GenomeUtils.Genome import TranscriptLocus
import pytest
import yaml
from ASOkai.Analysis import IntrinsicFeaturesAnalysis
from ASOkai.Sites import TranscriptSite
from ASOkai.Targets import TargetGene
from ASOkai._cwl.generation import StepCwlGenerator
from ASOkai.Plugins import CsvFile, FileInput, JsonFile
from ASOkai._pipeline.contracts.execution import StepInputBinding, StepRun
from ASOkai._pipeline.steps.analysis.intrinsic_features import IntrinsicFeaturesStep
from ASOkai._pipeline.steps.core.create_target_gene import CreateTargetGeneStep


@pytest.fixture
def config(tmp_path):
    return {
        "datadir": str(tmp_path),
        "parameters": {
            "genome": {
                "assembly": "GRCh38",
                "release": 114,
                "species": "Homo_sapiens",
            },
            "target": {"target_id": "ENSG00000133703", "k": 16, "region": "pre-mrna"},
        },
    }


@pytest.fixture
def step():
    return IntrinsicFeaturesStep()


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


def test_declares_intrinsic_analysis_contract(step):
    assert step.name == "compute-intrinsic-features"
    assert step.analysis_cls is IntrinsicFeaturesAnalysis
    assert step.dependencies == ["create-target-gene"]
    assert (
        step.spec.input("target_gene").source is CreateTargetGeneStep.target_gene_output
    )
    assert isinstance(step.spec.input("target_gene"), FileInput)
    assert isinstance(step.target_gene_input.file_type, JsonFile)
    assert step.target_gene_input.file_type.value_type is TargetGene
    file_type = step.intrinsic_features_output.file_type
    assert isinstance(file_type, CsvFile)
    assert file_type.index == {"site_id": str}
    assert file_type.columns == {
        "GC_content": float,
        "AT_content": float,
        "T_count": int,
        "CpG_count": int,
        "T_content": float,
        "CpG_content": float,
    }


def test_features_are_a_runtime_parameter(step):
    assert step.config_map == {
        "features": "parameters.analysis.intrinsic_features.features"
    }


def test_output_paths_structure(step, config, tmp_path):
    paths = _run(step, config, tmp_path).output_paths()
    expected = (
        tmp_path
        / "GRCh38"
        / "ensembl"
        / "114"
        / "targets"
        / "ENSG00000133703"
        / "analysis"
        / "intrinsic"
        / "ENSG00000133703_k16_pre-mrna_intrinsic_all.csv"
    )
    assert paths["intrinsic_features"] == expected


def test_output_paths_uses_target_name_fallback(step, tmp_path):
    config = {
        "datadir": str(tmp_path),
        "parameters": {
            "genome": {
                "assembly": "GRCh38",
                "release": 114,
                "species": "Homo_sapiens",
            },
            "target": {"target_name": "KRAS", "k": 16, "region": "pre-mrna"},
        },
    }
    paths = _run(step, config, tmp_path).output_paths()
    expected = (
        tmp_path
        / "GRCh38"
        / "ensembl"
        / "114"
        / "targets"
        / "KRAS"
        / "analysis"
        / "intrinsic"
        / "KRAS_k16_pre-mrna_intrinsic_all.csv"
    )
    assert paths["intrinsic_features"] == expected


def test_output_path_distinguishes_genome_releases(step, config, tmp_path):
    release_114 = _run(step, config, tmp_path).output_paths()
    config["parameters"]["genome"]["release"] = 115
    release_115 = _run(step, config, tmp_path).output_paths()

    assert release_114 != release_115
    assert "114" in release_114["intrinsic_features"].parts
    assert "115" in release_115["intrinsic_features"].parts


def test_cwl_spec_generates_command_line_tool(step, config, tmp_path):
    run = _run(step, config, tmp_path)
    doc = yaml.safe_load(StepCwlGenerator().render(run))

    assert set(doc["inputs"]) == {"target_gene", "features", "n_threads"}
    assert doc["inputs"]["target_gene"]["type"] == "File"
    assert "intrinsic_features_output" not in doc["inputs"]
    assert "intrinsic_features_filename" not in doc["inputs"]
    assert {
        "prefix": "--intrinsic-features-output",
        "valueFrom": "ENSG00000133703_k16_pre-mrna_intrinsic_all.csv",
    } in doc["arguments"]
    assert doc["outputs"]["intrinsic_features"]["outputBinding"]["glob"] == (
        "ENSG00000133703_k16_pre-mrna_intrinsic_all.csv"
    )


def test_selected_features_have_a_distinct_output_path(step, config, tmp_path):
    selected = StepRun(
        step.name,
        step,
        config,
        inputs=(StepInputBinding(step.target_gene_input, tmp_path / "target.json"),),
        parameters={"features": "GC_content,CpG_count"},
    )

    path = selected.output_paths()["intrinsic_features"]
    assert path.name.endswith("_intrinsic_GC_content,CpG_count.csv")
    assert selected.parameters["features"] == "GC_content,CpG_count"


@pytest.mark.parametrize("features", ["", "GC_content,", "unknown", "GC_content,GC_content"])
def test_rejects_invalid_feature_selection(step, config, tmp_path, features):
    with pytest.raises(ValueError, match="features|CSV"):
        StepRun(
            step.name,
            step,
            config,
            inputs=(StepInputBinding(step.target_gene_input, tmp_path / "target.json"),),
            parameters={"features": features},
        )


def test_run_cli_writes_site_keyed_results_as_csv_rows(tmp_path):
    site = TranscriptSite(
        id="site-1",
        loci=[TranscriptLocus("transcript-1", 0, 4)],
        sequence=Seq("GCGT"),
    )
    target = TargetGene(
        id="ENSG00000133703",
        name="KRAS",
        chr="12",
        start=1,
        end=4,
        strand="+",
        sequence=Seq("GCGT"),
        sites={site.id: site},
    )
    target_input = tmp_path / "target.json"
    CreateTargetGeneStep.target_gene_output.write(
        target_input,
        target,
    )

    output = tmp_path / "intrinsic.csv"
    result = IntrinsicFeaturesStep().run_cli(
        [
            "--target-gene",
            str(target_input),
            "--intrinsic-features-output",
            str(output),
        ]
    )

    assert result == 0
    assert IntrinsicFeaturesStep.intrinsic_features_output.file_type.read(output) == [
        {
            "site_id": "site-1",
            "GC_content": 0.75,
            "AT_content": 0.25,
            "T_count": 1,
            "CpG_count": 1,
            "T_content": 0.25,
            "CpG_content": 0.25,
        }
    ]


def test_run_cli_writes_only_selected_feature_columns(tmp_path):
    site = TranscriptSite(
        id="site-1",
        loci=[TranscriptLocus("transcript-1", 0, 4)],
        sequence=Seq("GCGT"),
    )
    target = TargetGene(
        id="ENSG00000133703",
        name="KRAS",
        chr="12",
        start=1,
        end=4,
        strand="+",
        sequence=Seq("GCGT"),
        sites={site.id: site},
    )
    target_input = tmp_path / "target.json"
    CreateTargetGeneStep.target_gene_output.write(target_input, target)
    output = tmp_path / "selected.csv"

    result = IntrinsicFeaturesStep().run_cli(
        [
            "--target-gene", str(target_input),
            "--intrinsic-features-output", str(output),
            "--features", "GC_content,CpG_count",
        ]
    )

    assert result == 0
    assert output.read_text() == "site_id,GC_content,CpG_count\nsite-1,0.75,1\n"
    assert IntrinsicFeaturesStep.intrinsic_features_output.file_type.read(output) == [
        {"site_id": "site-1", "GC_content": 0.75, "CpG_count": 1}
    ]
