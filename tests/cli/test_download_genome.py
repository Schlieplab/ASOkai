#!/usr/bin/env python
"""
Tests for download_genome CLI.
"""
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from ASOkai.cli.download_genome import load_config, run


@pytest.mark.cli
class TestLoadConfig:
    """Test config loading."""

    def test_load_config_valid_yaml(self, temp_dir):
        """Test loading valid YAML config."""
        config_path = temp_dir / "config.yaml"
        config_path.write_text("genome:\n  assembly_id: GRCh38\n  species: homo_sapiens\n")
        result = load_config(config_path)
        assert result["genome"]["assembly_id"] == "GRCh38"
        assert result["genome"]["species"] == "homo_sapiens"

    def test_load_config_empty_returns_empty_dict(self, temp_dir):
        """Test empty file returns empty dict."""
        config_path = temp_dir / "empty.yaml"
        config_path.write_text("")
        result = load_config(config_path)
        assert result == {}

    def test_load_config_with_overrides(self, temp_dir):
        """Test config with genome overrides."""
        config_path = temp_dir / "config.yaml"
        config_path.write_text(
            "genome:\n  assembly_id: GRCh39\n  ensembl_release: 120\n  species: mus_musculus\n"
        )
        result = load_config(config_path)
        assert result["genome"]["assembly_id"] == "GRCh39"
        assert result["genome"]["ensembl_release"] == 120
        assert result["genome"]["species"] == "mus_musculus"


@pytest.mark.cli
class TestRun:
    """Test run() with mocked downloader."""

    @patch("ASOkai.cli.download_genome.GenomeUtils.Downloaders.EnsemblGenomeDownloader")
    def test_run_passes_correct_params_to_downloader(self, mock_downloader_class, temp_dir):
        """Test that run() instantiates downloader with correct params and calls download()."""
        mock_downloader = MagicMock()
        mock_downloader.download.return_value = {"dna": Path("/fake/dna.fa")}
        mock_downloader_class.return_value = mock_downloader

        result = run(
            output_dir=temp_dir,
            assembly_id="GRCh38",
            ensembl_release=115,
            species="homo_sapiens",
        )

        mock_downloader_class.assert_called_once_with(
            assembly_id="GRCh38",
            ensembl_release=115,
            species="homo_sapiens",
            genomes_root_dir=temp_dir,
        )
        mock_downloader.download.assert_called_once()
        assert result == {"dna": Path("/fake/dna.fa")}

    @patch("ASOkai.cli.download_genome.GenomeUtils.Downloaders.EnsemblGenomeDownloader")
    def test_run_uses_defaults(self, mock_downloader_class, temp_dir):
        """Test that run() uses default assembly_id, ensembl_release, species."""
        mock_downloader = MagicMock()
        mock_downloader.download.return_value = {}
        mock_downloader_class.return_value = mock_downloader

        run(output_dir=temp_dir)

        mock_downloader_class.assert_called_once_with(
            assembly_id="GRCh38",
            ensembl_release=115,
            species="homo_sapiens",
            genomes_root_dir=temp_dir,
        )
