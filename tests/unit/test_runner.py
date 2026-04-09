"""Tests for pipeline runner logic."""
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from pipeline import runner


@pytest.fixture
def config(tmp_path):
    return {
        "datadir": str(tmp_path),
        "genome": {
            "assembly_id": "GRCh38",
            "ensembl_release": 114,
            "species": "Homo_sapiens",
        },
    }


def test_run_step_unknown_step(config):
    with pytest.raises(ValueError, match="Unknown step 'nonexistent'"):
        runner.run_step("nonexistent", config)


def test_run_step_skips_when_outputs_exist(config, tmp_path):
    from pipeline.steps.download_genome import DownloadGenomeStep
    step = DownloadGenomeStep()
    base = tmp_path / "genomes" / "ensembl" / "GRCh38" / "114"
    base.mkdir(parents=True)
    for p in step.output_paths(config).values():
        p.touch()

    with patch("pipeline.runner._toil_run") as mock_toil:
        result = runner.run_step("download-genome", config)
        mock_toil.assert_not_called()
    assert result is not None


def test_run_step_dry_run_returns_outputs(config):
    result = runner.run_step("download-genome", config, dry_run=True, force=True)
    assert result is not None
    assert "dna" in result
    assert "cdna" in result
    assert "annotation" in result


def test_run_step_dry_run_does_not_call_toil(config):
    with patch("pipeline.runner._toil_run") as mock_toil:
        runner.run_step("download-genome", config, dry_run=True, force=True)
        mock_toil.assert_not_called()


def test_run_step_force_does_not_cleanup_on_dry_run(config, tmp_path):
    from pipeline.steps.download_genome import DownloadGenomeStep
    step = DownloadGenomeStep()
    base = tmp_path / "genomes" / "ensembl" / "GRCh38" / "114"
    base.mkdir(parents=True)
    for p in step.output_paths(config).values():
        p.touch()

    with patch("pipeline.runner._toil_run"):
        runner.run_step("download-genome", config, force=True, dry_run=True)

    assert step.outputs_exist(config) is True


def test_run_step_missing_dependency_raises(config):
    from pipeline.steps.download_genome import DownloadGenomeStep

    step = DownloadGenomeStep()
    step.dependencies = ["build-genome"]

    # build-genome must conform to Step protocol to pass runner validation
    mock_build = MagicMock()
    mock_build.name = "build-genome"
    mock_build.description = ""
    mock_build.dependencies = []
    mock_build.config_map = {}
    mock_build.cwl_path = "/fake/path"
    mock_build.outdir = lambda c: Path(".")
    mock_build.output_paths = lambda c: {}
    mock_build.outputs_exist = lambda c: False
    mock_build.cleanup = lambda c: None

    with patch("pipeline.runner.get_steps") as mock_registry:
        mock_registry.return_value = {
            "download-genome": step,
            "build-genome": mock_build,
        }
        with pytest.raises(RuntimeError, match="requires 'build-genome'"):
            runner.run_step("download-genome", config, recursive=False)
