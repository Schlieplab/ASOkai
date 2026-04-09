"""Tests for pipeline config loading and resolution."""
import pytest
from pathlib import Path
from pipeline import config as cfg


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
