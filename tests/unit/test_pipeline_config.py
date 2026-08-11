#!/usr/bin/env python
"""Tests for pipeline config loading and resolution."""

from pathlib import Path

import pytest

from ASOkai._pipeline import config as cfg
from ASOkai._pipeline.steps.core.download_genome import DownloadGenomeStep
from ASOkai._pipeline.steps.core.generate_antisense_candidates import (
    GenerateAntisenseCandidatesStep,
)


@pytest.fixture
def sample_config(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "datadir: ./data\n"
        "genome:\n"
        "  assembly_id: GRCh38\n"
        "  ensembl_release: 114\n"
        "  species: Homo_sapiens\n"
    )
    return config_file


def test_load(sample_config):
    config = cfg.load(sample_config)
    assert config["datadir"] == "./data"
    assert config["genome"]["assembly_id"] == "GRCh38"


@pytest.mark.parametrize("content", ["", "- one\n- two\n"])
def test_load_rejects_non_mapping_root(tmp_path, content):
    path = tmp_path / "config.yaml"
    path.write_text(content)

    with pytest.raises(ValueError, match="mapping at its root"):
        cfg.load(path)


def test_load_rejects_invalid_yaml(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("genome: [")

    with pytest.raises(ValueError, match="Invalid YAML configuration"):
        cfg.load(path)


def test_resolve_top_level(sample_config):
    config = cfg.load(sample_config)
    assert cfg.resolve(config, "datadir") == "./data"


def test_resolve_nested(sample_config):
    config = cfg.load(sample_config)
    assert cfg.resolve(config, "genome.assembly_id") == "GRCh38"
    assert cfg.resolve(config, "genome.ensembl_release") == 114


def test_resolve_missing_key(sample_config):
    config = cfg.load(sample_config)
    with pytest.raises(KeyError, match="genome.nonexistent"):
        cfg.resolve(config, "genome.nonexistent")


def test_apply_overrides(sample_config):
    config = cfg.load(sample_config)
    cfg.apply_overrides(config, {"genome.ensembl_release": 115})
    assert config["genome"]["ensembl_release"] == 115


def test_apply_overrides_new_key(sample_config):
    config = cfg.load(sample_config)
    cfg.apply_overrides(config, {"genome.new_key": "value"})
    assert config["genome"]["new_key"] == "value"


def test_apply_overrides_rejects_scalar_parent(sample_config):
    config = cfg.load(sample_config)

    with pytest.raises(ValueError, match="cannot descend.*assembly_id"):
        cfg.apply_overrides(
            config,
            {"genome.assembly_id.version": 2},
        )


def test_load_validates_against_checked_in_schema(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        "datadir: ./data\n"
        "genome:\n"
        "  source: ''\n"
    )

    with pytest.raises(
        ValueError,
        match=r"genome.source",
    ):
        cfg.load(path)


def test_config_schema_leaves_supported_values_to_selected_steps(tmp_path):
    cfg.validate_config_schema(
        {
            "datadir": str(tmp_path),
            "antisense": {
                "modality": "sirna",
                "mechanism": "risc",
                "chemistry": {"type": "custom"},
            },
        }
    )


def test_config_schema_allows_plugin_namespaces(tmp_path):
    cfg.validate_config_schema(
        {
            "datadir": str(tmp_path),
            "example_plugin": {
                "threshold": 0.5,
            },
        }
    )


def test_config_schema_uses_installed_plugin_schemas(
    tmp_path,
    monkeypatch,
):
    schema_path = tmp_path / "config.schema.yaml"
    schema_path.write_text(
        "type: object\n"
        "properties:\n"
        "  example_plugin:\n"
        "    type: object\n"
        "    properties:\n"
        "      threshold:\n"
        "        type: number\n"
        "        maximum: 1\n"
    )
    monkeypatch.setattr(
        "ASOkai.Plugins._registry.get_config_schema_paths",
        lambda: {"example": schema_path},
    )

    with pytest.raises(
        ValueError,
        match=r"Plugin 'example' schema.*example_plugin.threshold",
    ):
        cfg.validate_config_schema(
            {
                "datadir": str(tmp_path),
                "example_plugin": {
                    "threshold": 2,
                },
            }
        )


def test_validate_step_config_uses_defaults_and_only_selected_steps(
    sample_config,
):
    config = cfg.load(sample_config)
    step = DownloadGenomeStep()

    cfg.validate_step_config(config, [step])

    assert step.output_relative_path("dna", config).parts[2] == "ensembl"


def test_validate_step_config_requires_selected_step_parameters(tmp_path):
    with pytest.raises(ValueError) as raised:
        cfg.validate_step_config(
            {"datadir": str(tmp_path)},
            [DownloadGenomeStep()],
        )

    message = str(raised.value)
    assert "$.genome.assembly_id" in message
    assert "$.genome.ensembl_release" in message
    assert "$.genome.species" in message
    assert "$.genome.source" not in message


def test_config_schema_reports_all_errors(tmp_path):
    config = {
        "datadir": str(tmp_path),
        "genome": {
            "assembly_id": "",
            "ensembl_release": 0,
            "species": "Homo_sapiens",
        },
    }

    with pytest.raises(ValueError) as raised:
        cfg.validate_config_schema(config)

    message = str(raised.value)
    assert "$.genome.assembly_id" in message
    assert "$.genome.ensembl_release" in message


def test_config_schema_requires_one_target_identifier(
    tmp_path,
):
    config = {
        "datadir": str(tmp_path),
        "genome": {
            "assembly_id": "GRCh38",
            "ensembl_release": 114,
            "species": "Homo_sapiens",
        },
        "target": {
            "k": 16,
            "region": "pre-mrna",
        },
    }

    with pytest.raises(
        ValueError,
        match=r"exactly one.*target.target_id, target.target_name",
    ):
        cfg.validate_config_schema(config)


def test_config_schema_rejects_two_target_identifiers(tmp_path):
    with pytest.raises(
        ValueError,
        match=r"exactly one.*target.target_id, target.target_name",
    ):
        cfg.validate_config_schema(
            {
                "datadir": str(tmp_path),
                "target": {
                    "target_id": "ENSG1",
                    "target_name": "KRAS",
                },
            }
        )


@pytest.mark.parametrize("layout", ["", "16", "3-10", "3-10-3-1", "0-16-0", "a-b-c"])
def test_config_schema_rejects_invalid_chemistry_layout(layout):
    with pytest.raises(ValueError, match="antisense.chemistry.layout"):
        cfg.validate_config_schema(
            {
                "datadir": ".",
                "antisense": {"chemistry": {"layout": layout}},
            }
        )


def test_config_schema_requires_layout_to_match_target_length():
    with pytest.raises(ValueError, match=r"segment lengths must sum to target.k \(18\)"):
        cfg.validate_config_schema(
            {
                "datadir": ".",
                "target": {"target_id": "ENSG1", "k": 18},
                "antisense": {
                    "chemistry": {
                        "type": "gapmer",
                        "layout": "3-10-3",
                    }
                },
            }
        )


def test_validate_step_config_rejects_missing_override_file(tmp_path):
    config = {
        "datadir": str(tmp_path),
        "genome": {"assembly_id": "GRCh38"},
        "target": {
            "target_id": "ENSG1",
            "k": 16,
            "region": "pre-mrna",
            "target_gene_path": str(tmp_path / "missing.json"),
        },
        "antisense": {
            "modality": "aso",
            "mechanism": "rnase-h1",
            "chemistry": {
                "type": "gapmer",
                "layout": "3-10-3",
            },
        },
    }

    with pytest.raises(ValueError, match="file does not exist"):
        cfg.validate_step_config(
            config,
            [GenerateAntisenseCandidatesStep()],
        )


def test_validate_step_config_checks_override_file_contents(tmp_path):
    override = tmp_path / "target.json"
    override.write_text("{not-json")
    config = {
        "datadir": str(tmp_path),
        "genome": {"assembly_id": "GRCh38"},
        "target": {
            "target_id": "ENSG1",
            "k": 16,
            "region": "pre-mrna",
            "target_gene_path": str(override),
        },
        "antisense": {
            "modality": "aso",
            "mechanism": "rnase-h1",
            "chemistry": {
                "type": "gapmer",
                "layout": "3-10-3",
            },
        },
    }

    with pytest.raises(ValueError, match="Invalid JSON"):
        cfg.validate_step_config(
            config,
            [GenerateAntisenseCandidatesStep()],
        )


def test_validate_step_config_rejects_datadir_file(tmp_path):
    datadir = tmp_path / "data"
    datadir.touch()

    with pytest.raises(ValueError, match="datadir.*not a directory"):
        cfg.validate_step_config(
            {
                "datadir": str(datadir),
                "genome": {
                    "assembly_id": "GRCh38",
                    "ensembl_release": 114,
                    "species": "Homo_sapiens",
                },
            },
            [DownloadGenomeStep()],
        )


def test_step_resources_returns_supported_fields():
    config = {
        "resources": {
            "analysis": {
                "n_processes": 4,
                "memory_mb": 8192,
            }
        }
    }

    assert cfg.step_resources(config, "analysis") == {
        "n_processes": 4,
        "memory_mb": 8192,
    }


def test_step_resources_uses_builtin_defaults_without_configuration():
    expected = {"n_processes": 1, "memory_mb": 4096}
    assert cfg.step_resources({}, "analysis") == expected
    assert cfg.step_resources({"resources": {}}, "analysis") == expected


def test_step_resources_merges_configured_defaults_and_step_overrides():
    config = {
        "resources": {
            "default": {
                "n_processes": 2,
                "memory_mb": 2048,
            },
            "analysis": {"n_processes": 8},
        }
    }

    assert cfg.step_resources(config, "analysis") == {
        "n_processes": 8,
        "memory_mb": 2048,
    }
    assert cfg.step_resources(config, "unconfigured") == {
        "n_processes": 2,
        "memory_mb": 2048,
    }


@pytest.mark.parametrize("section", ["default", "analysis"])
def test_config_schema_rejects_unsupported_resource_fields(section):
    config = {
        "datadir": ".",
        "resources": {section: {"nodes": 2}},
    }

    with pytest.raises(ValueError, match=rf"resources.{section}.*nodes"):
        cfg.validate_config_schema(config)


@pytest.mark.parametrize("key", ["n_processes", "memory_mb"])
@pytest.mark.parametrize("value", [True, 0, -1, 1.5, "4"])
def test_config_schema_rejects_invalid_resource_values(key, value):
    config = {
        "datadir": ".",
        "resources": {"analysis": {key: value}},
    }

    with pytest.raises(ValueError, match=rf"resources.analysis.{key}"):
        cfg.validate_config_schema(config)


@pytest.mark.parametrize(
    "resources",
    [[], {"analysis": 4}, {"default": 4}],
)
def test_config_schema_rejects_non_mapping_resources(resources):
    with pytest.raises(ValueError, match="resources"):
        cfg.validate_config_schema(
            {
                "datadir": ".",
                "resources": resources,
            }
        )
