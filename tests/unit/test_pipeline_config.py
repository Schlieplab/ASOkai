#!/usr/bin/env python
"""Tests for pipeline config loading and resolution."""

from pathlib import Path

import pytest

from ASOkai._pipeline import config as cfg
from ASOkai._pipeline.steps.analysis.intrinsic_features import (
    IntrinsicFeaturesStep,
)
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
                "design": {"type": "custom"},
            },
        }
    )


def test_selected_step_rejects_an_unsupported_design(tmp_path):
    config = {
        "datadir": str(tmp_path),
        "genome": {"assembly_id": "GRCh38"},
        "target": {
            "target_id": "ENSG1",
            "k": 16,
            "region": "pre-mrna",
        },
        "antisense": {
            "modality": "aso",
            "mechanism": "rnase-h1",
            "design": {"type": "custom"},
        },
    }

    with pytest.raises(
        ValueError,
        match=r"antisense.design.type.*unmodified.*gapmer",
    ):
        cfg.validate_step_config(
            config,
            [GenerateAntisenseCandidatesStep()],
        )


def test_selected_step_accepts_an_unmodified_aso_design(tmp_path):
    config = {
        "datadir": str(tmp_path),
        "genome": {"assembly_id": "GRCh38"},
        "target": {
            "target_id": "ENSG1",
            "k": 16,
            "region": "pre-mrna",
        },
        "antisense": {
            "modality": "aso",
            "mechanism": "rnase-h1",
            "design": {"type": "unmodified"},
        },
    }

    cfg.validate_config_schema(config)
    cfg.validate_step_config(
        config,
        [GenerateAntisenseCandidatesStep()],
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


@pytest.mark.parametrize(
    "input_configuration",
    [
        {},
        {"parameters": {}},
        {
            "path_override": "target.json",
            "parameters": {"region": "pre-mrna"},
        },
    ],
)
def test_config_schema_rejects_invalid_step_input_configuration(
    tmp_path,
    input_configuration,
):
    with pytest.raises(ValueError, match="intrinsic-features.*target_gene"):
        cfg.validate_config_schema(
            {
                "datadir": str(tmp_path),
                "steps": {
                    "intrinsic-features": {
                        "inputs": {
                            "target_gene": input_configuration,
                        },
                    },
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


@pytest.mark.parametrize(
    "field",
    ["left_wing_length", "gap_length", "right_wing_length"],
)
@pytest.mark.parametrize("value", [True, 0, -1, 1.5, "3"])
def test_config_schema_rejects_invalid_gapmer_segment_lengths(field, value):
    with pytest.raises(ValueError, match=rf"antisense.design.{field}"):
        cfg.validate_config_schema(
            {
                "datadir": ".",
                "antisense": {
                    "design": {
                        "type": "gapmer",
                        "left_wing_length": 3,
                        "gap_length": 10,
                        "right_wing_length": 3,
                        field: value,
                    }
                },
            }
        )


@pytest.mark.parametrize(
    "missing_field",
    ["left_wing_length", "gap_length", "right_wing_length"],
)
def test_config_schema_requires_every_gapmer_segment_length(missing_field):
    design = {
        "type": "gapmer",
        "left_wing_length": 3,
        "gap_length": 10,
        "right_wing_length": 3,
    }
    del design[missing_field]

    with pytest.raises(ValueError, match=rf"antisense.design.*{missing_field}"):
        cfg.validate_config_schema(
            {
                "datadir": ".",
                "antisense": {"design": design},
            }
        )


def test_config_schema_rejects_gapmer_lengths_for_unmodified_aso():
    with pytest.raises(ValueError, match="antisense.design"):
        cfg.validate_config_schema(
            {
                "datadir": ".",
                "antisense": {
                    "design": {
                        "type": "unmodified",
                        "gap_length": 10,
                    }
                },
            }
        )


def test_selected_step_requires_gapmer_segments_to_match_target_length(
    tmp_path,
):
    config = {
        "datadir": str(tmp_path),
        "genome": {"assembly_id": "GRCh38"},
        "target": {
            "target_id": "ENSG1",
            "k": 18,
            "region": "pre-mrna",
        },
        "antisense": {
            "modality": "aso",
            "mechanism": "rnase-h1",
            "design": {
                "type": "gapmer",
                "left_wing_length": 3,
                "gap_length": 10,
                "right_wing_length": 3,
            },
        },
    }

    cfg.validate_config_schema(config)
    with pytest.raises(
        ValueError,
        match=r"generate-antisense-candidates.*target-site length \(18\)",
    ):
        cfg.validate_step_config(
            config,
            [GenerateAntisenseCandidatesStep()],
        )


def test_validate_step_config_rejects_missing_override_file(tmp_path):
    config = {
        "datadir": str(tmp_path),
        "genome": {"assembly_id": "GRCh38"},
        "target": {
            "target_id": "ENSG1",
            "k": 16,
            "region": "pre-mrna",
        },
        "steps": {
            "generate-antisense-candidates": {
                "inputs": {
                    "target_gene": {
                        "path_override": str(tmp_path / "missing.json"),
                    },
                },
            },
        },
        "antisense": {
            "modality": "aso",
            "mechanism": "rnase-h1",
            "design": {
                "type": "gapmer",
                "left_wing_length": 3,
                "gap_length": 10,
                "right_wing_length": 3,
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
        },
        "steps": {
            "generate-antisense-candidates": {
                "inputs": {
                    "target_gene": {"path_override": str(override)},
                },
            },
        },
        "antisense": {
            "modality": "aso",
            "mechanism": "rnase-h1",
            "design": {
                "type": "gapmer",
                "left_wing_length": 3,
                "gap_length": 10,
                "right_wing_length": 3,
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
    step = IntrinsicFeaturesStep()
    config = {
        "resources": {
            step.name: {
                "n_processes": 4,
                "memory_mb": 8192,
            }
        }
    }

    assert cfg.step_resources(config, step) == {
        "n_processes": 4,
        "memory_mb": 8192,
    }


def test_step_resources_uses_builtin_defaults_without_configuration():
    analysis = IntrinsicFeaturesStep()
    download = DownloadGenomeStep()

    assert cfg.step_resources({}, analysis) == {
        "n_processes": 1,
        "memory_mb": 4096,
    }
    assert cfg.step_resources({"resources": {}}, download) == {
        "memory_mb": 4096,
    }


def test_step_resources_merges_configured_defaults_and_step_overrides():
    analysis = IntrinsicFeaturesStep()
    download = DownloadGenomeStep()
    config = {
        "resources": {
            "default": {
                "n_processes": 2,
                "memory_mb": 2048,
            },
            analysis.name: {"n_processes": 8},
        }
    }

    assert cfg.step_resources(config, analysis) == {
        "n_processes": 8,
        "memory_mb": 2048,
    }
    assert cfg.step_resources(config, download) == {
        "memory_mb": 2048,
    }


def test_selected_step_rejects_unsupported_process_setting(
    sample_config,
):
    config = cfg.load(sample_config)
    config["resources"] = {
        "download-genome": {"n_processes": 2},
    }
    cfg.validate_config_schema(config)

    with pytest.raises(
        ValueError,
        match=r"resources.download-genome.n_processes.*does not support",
    ):
        cfg.validate_step_config(config, [DownloadGenomeStep()])


def test_default_process_setting_is_only_applied_to_supported_steps(
    sample_config,
):
    config = cfg.load(sample_config)
    config["resources"] = {
        "default": {"n_processes": 4},
    }

    cfg.validate_config_schema(config)
    cfg.validate_step_config(config, [DownloadGenomeStep()])
    assert cfg.step_resources(config, DownloadGenomeStep()) == {
        "memory_mb": 4096,
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
