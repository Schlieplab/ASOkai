#!/usr/bin/env python
"""Tests for pipeline config loading and resolution."""
import pytest
from pathlib import Path
from ASOkai._pipeline import config as cfg


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
def test_step_resources_rejects_unsupported_fields(section):
    config = {"resources": {section: {"nodes": 2}}}

    with pytest.raises(ValueError, match=rf"resources.{section}.*nodes"):
        cfg.step_resources(config, "analysis")


@pytest.mark.parametrize("key", ["n_processes", "memory_mb"])
@pytest.mark.parametrize("value", [True, 0, -1, 1.5, "4"])
def test_step_resources_rejects_invalid_supported_values(key, value):
    config = {"resources": {"analysis": {key: value}}}

    with pytest.raises(ValueError, match=rf"resources.analysis.{key}"):
        cfg.step_resources(config, "analysis")


def test_step_resources_rejects_non_mapping_sections():
    with pytest.raises(TypeError, match="resources.*mapping"):
        cfg.step_resources({"resources": []}, "analysis")

    with pytest.raises(TypeError, match="resources.analysis.*mapping"):
        cfg.step_resources({"resources": {"analysis": 4}}, "analysis")

    with pytest.raises(TypeError, match="resources.default.*mapping"):
        cfg.step_resources({"resources": {"default": 4}}, "analysis")
