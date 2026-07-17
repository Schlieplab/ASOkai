#!/usr/bin/env python
"""Tests for IntrinsicFeaturesStep."""
import json
import pytest
from pathlib import Path
import yaml
from ASOkai.Analysis import IntrinsicFeaturesAnalysis, SiteSpecificAnalysis
from ASOkai._cwl.spec import StepCwlGenerator
from ASOkai._pipeline.steps.intrinsic_features import IntrinsicFeaturesStep
from ASOkai._pipeline.base import (
    AnalysisStep,
    Step,
)


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
    assert isinstance(step, AnalysisStep)
    assert step.analysis_cls is IntrinsicFeaturesAnalysis


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


def test_cwl_spec_generates_command_line_tool(step):
    doc = yaml.safe_load(StepCwlGenerator().render(step))

    assert doc["class"] == "CommandLineTool"
    assert doc["baseCommand"] == ["ASOkai", "step", "intrinsic-features"]
    assert doc["inputs"]["target_gene"]["type"] == "File"
    assert doc["inputs"]["region"]["type"]["type"] == "enum"
    assert "intrinsic_features_output" not in doc["inputs"]
    assert "intrinsic_features_filename" not in doc["inputs"]
    assert {
        "prefix": "--intrinsic-features-output",
        "valueFrom": "intrinsic_features.json",
    } in doc["arguments"]
    assert doc["outputs"]["intrinsic_features"]["outputBinding"]["glob"] == (
        "intrinsic_features.json"
    )


def test_main_rejects_missing_target_identifier_before_analysis(tmp_path):
    from ASOkai._pipeline.steps import intrinsic_features

    with pytest.raises(SystemExit) as excinfo:
        intrinsic_features.main(
            [
                "--target-gene", str(tmp_path / "target.json"),
                "--assembly", "GRCh38",
                "--k", "16",
                "--region", "pre-mrna",
                "--intrinsic-features-output", str(tmp_path / "intrinsic.json"),
            ]
        )

    assert excinfo.value.code == 2


def test_intrinsic_features_analysis_returns_site_keyed_results():
    class FakeSite:
        def __init__(self, id, sequence):
            self.id = id
            self.sequence = sequence

    sites = [
        FakeSite("site-1", "GCGT"),
        FakeSite("site-2", "TTAA"),
    ]

    analysis = IntrinsicFeaturesAnalysis(sites=sites)

    assert isinstance(analysis, SiteSpecificAnalysis)
    assert analysis.run() == {
        "site-1": {
            "GC_content": 0.75,
            "AT_content": 0.25,
            "T_count": 1,
            "CpG_count": 1,
            "T_content": 0.25,
            "CpG_content": 0.25,
        },
        "site-2": {
            "GC_content": 0.0,
            "AT_content": 1.0,
            "T_count": 2,
            "CpG_count": 0,
            "T_content": 0.5,
            "CpG_content": 0.0,
        },
    }


def test_intrinsic_features_analysis_analyzes_one_site():
    class FakeSite:
        id = "site-1"
        sequence = "GCGT"

    assert IntrinsicFeaturesAnalysis(sites=[FakeSite()]).analyze(FakeSite()) == {
        "GC_content": 0.75,
        "AT_content": 0.25,
        "T_count": 1,
        "CpG_count": 1,
        "T_content": 0.25,
        "CpG_content": 0.25,
    }


def test_main_writes_metadata_with_site_keyed_results(monkeypatch, tmp_path):
    from ASOkai._pipeline.steps import intrinsic_features
    from ASOkai.Targets import TargetGene

    class FakeSite:
        def __init__(self, id, sequence):
            self.id = id
            self.sequence = sequence

    class FakeTargetGene:
        sites = [FakeSite("site-1", "GCGT")]

    monkeypatch.setattr(
        TargetGene,
        "from_file",
        classmethod(lambda cls, path: FakeTargetGene()),
    )

    output = tmp_path / "intrinsic.json"
    result = intrinsic_features.main(
        [
            "--target-gene", str(tmp_path / "target.json"),
            "--assembly", "GRCh38",
            "--target-id", "ENSG00000133703",
            "--k", "16",
            "--region", "pre-mrna",
            "--intrinsic-features-output", str(output),
        ]
    )

    payload = json.loads(output.read_text())
    assert result == 0
    assert payload["analysis"] == "intrinsic-features"
    assert payload["assembly"] == "GRCh38"
    assert payload["target_id"] == "ENSG00000133703"
    assert payload["k"] == 16
    assert payload["region"] == "pre-mrna"
    assert payload["results"]["site-1"]["GC_content"] == 0.75
    assert payload["results"]["site-1"]["T_count"] == 1
