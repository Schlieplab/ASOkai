#!/usr/bin/env python
"""Tests for pipeline runner logic."""
import pytest
import yaml
from pathlib import Path
from typing import ClassVar
from unittest.mock import patch, MagicMock
from ASOkai._cwl.spec import StepSpec
from ASOkai._pipeline import runner
from ASOkai._cwl.executors import CwlToolExecutor, ToilExecutor
from ASOkai._pipeline.base import Runnable, Step
from ASOkai._pipeline.plan import ExecutionPlan


@pytest.fixture
def config(tmp_path):
    return {
        "datadir": str(tmp_path),
        "genome": {
            "assembly_id": "GRCh38",
            "ensembl_release": 114,
            "source": "ensembl",
            "species": "Homo_sapiens",
        },
    }


def _materializing_executor(*filenames):
    executor = MagicMock()

    def run(cwl_path, _inputs, outdir):
        outdir.mkdir(parents=True, exist_ok=True)
        layout = yaml.safe_load(
            (Path(cwl_path).parent / "output-layout.yml").read_text()
        )
        for filename, output in zip(filenames, layout["outputs"]):
            path = outdir / output["destination"]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(filename)

    executor.run.side_effect = run
    return executor


def test_run_step_unknown_step(config):
    with pytest.raises(ValueError, match="Unknown step 'nonexistent'"):
        runner.run_step("nonexistent", config)


def test_run_step_skips_when_outputs_exist(config, tmp_path):
    from ASOkai._pipeline.steps.download_genome import DownloadGenomeStep
    step = DownloadGenomeStep()
    base = tmp_path / "GRCh38" / "genomes" / "ensembl" / "114"
    base.mkdir(parents=True)
    for p in step.output_paths(config).values():
        p.touch()

    with patch("ASOkai._cwl.executors.CwlToolExecutor.run") as mock_run:
        result = runner.run_step("download-genome", config)
        mock_run.assert_not_called()
    assert result is not None


def test_run_step_dry_run_returns_outputs(config):
    result = runner.run_step("download-genome", config, dry_run=True, force=True)
    assert result is not None
    assert "dna" in result
    assert "cdna" in result
    assert "annotation" in result


def test_run_step_dry_run_does_not_call_default_executor(config):
    with patch("ASOkai._cwl.executors.CwlToolExecutor.run") as mock_run:
        runner.run_step("download-genome", config, dry_run=True, force=True)
        mock_run.assert_not_called()


def test_run_step_uses_injected_executor(config):
    executor = _materializing_executor("dna.fa.gz", "cdna.fa.gz", "annotation.gtf.gz", "annotation.db")

    runner.run_step("download-genome", config, force=True, executor=executor)

    executor.run.assert_called_once()


def test_run_step_writes_job_bundle_before_execution(config, tmp_path):
    executor = _materializing_executor("dna.fa.gz", "cdna.fa.gz", "annotation.gtf.gz", "annotation.db")

    runner.run_step("download-genome", config, force=True, executor=executor)

    export_dirs = list((tmp_path / "jobs").glob("asokai-job-*"))
    assert len(export_dirs) == 1
    job_path, inputs, output_dir = executor.run.call_args.args
    assert job_path == str(export_dirs[0] / "run.cwl")
    assert output_dir == tmp_path
    assert (export_dirs[0] / "job.yml").exists()
    assert (export_dirs[0] / "publish.cwl").exists()
    assert (export_dirs[0] / "output-layout.yml").exists()
    assert (export_dirs[0] / "steps" / "download-genome.cwl").exists()
    assert inputs["assembly"] == "GRCh38"
    from ASOkai._pipeline.steps.download_genome import DownloadGenomeStep
    assert all(DownloadGenomeStep().output_paths(config)[name].exists() for name in (
        "dna", "cdna", "annotation", "db"
    ))


def test_run_step_rejects_missing_published_outputs(config):
    from ASOkai._pipeline.steps.download_genome import DownloadGenomeStep

    executor = _materializing_executor("dna.fa.gz")

    with pytest.raises(RuntimeError, match="did not publish expected output"):
        runner.run_step("download-genome", config, force=True, executor=executor)

    paths = DownloadGenomeStep().output_paths(config)
    assert paths["dna"].exists()
    assert not paths["cdna"].exists()


def test_run_step_uses_config_download_source(config):
    executor = _materializing_executor("dna.fa.gz", "cdna.fa.gz", "annotation.gtf.gz", "annotation.db")

    runner.run_step("download-genome", config, force=True, executor=executor)

    _, inputs, _ = executor.run.call_args.args
    assert inputs["source"] == "ensembl"


def test_run_step_uses_configured_download_source(config):
    executor = _materializing_executor("dna.fa.gz", "cdna.fa.gz", "annotation.gtf.gz", "annotation.db")
    config["genome"]["source"] = "ucsc"

    runner.run_step("download-genome", config, force=True, executor=executor)

    _, inputs, _ = executor.run.call_args.args
    assert inputs["source"] == "ucsc"


def test_run_step_force_does_not_cleanup_on_dry_run(config, tmp_path):
    from ASOkai._pipeline.steps.download_genome import DownloadGenomeStep
    step = DownloadGenomeStep()
    base = tmp_path / "GRCh38" / "genomes" / "ensembl" / "114"
    base.mkdir(parents=True)
    for p in step.output_paths(config).values():
        p.touch()

    with patch("ASOkai._cwl.executors.CwlToolExecutor.run"):
        runner.run_step("download-genome", config, force=True, dry_run=True)

    assert step.outputs_exist(config) is True


def test_run_step_missing_dependency_raises(config, monkeypatch):
    from ASOkai._pipeline.steps.download_genome import DownloadGenomeStep

    step = DownloadGenomeStep()
    monkeypatch.setattr(DownloadGenomeStep, "dependencies", ["build-genome"])

    # build-genome must conform to Step protocol to pass runner validation
    class MockBuildStep:
        name = "build-genome"
        description = ""
        cli_module = "tests.fake_step"
        dependencies = []
        spec = StepSpec()

        def output_paths(self, c):
            return {}

        def outputs_exist(self, c):
            return False

        def cleanup(self, c):
            return None

    mock_build = MockBuildStep()

    registry = {
        "download-genome": step,
        "build-genome": mock_build,
    }
    with patch("ASOkai._pipeline.runner.get_steps", return_value=registry), \
         patch("ASOkai._pipeline.registry.get_steps", return_value=registry):
        with pytest.raises(RuntimeError, match="requires 'build-genome'"):
            runner.run_step("download-genome", config, recursive=False)


@pytest.fixture
def workflow_config(tmp_path):
    return {
        "datadir": str(tmp_path),
        "genome": {
            "assembly_id": "GRCh38",
            "ensembl_release": 114,
            "source": "ensembl",
            "species": "Homo_sapiens",
        },
        "target": {
            "target_id": "ENSG00000133703",
            "target_name": "KRAS",
            "k": 16,
            "region": "pre-mrna",
        },
    }


def test_run_workflow_unknown_raises(workflow_config):
    with pytest.raises(ValueError, match="Unknown workflow 'nonexistent'"):
        runner.run_workflow("nonexistent", workflow_config)


def test_run_workflow_dry_run_does_not_call_default_executor(workflow_config):
    with patch("ASOkai._cwl.executors.CwlToolExecutor.run") as mock_run:
        runner.run_workflow("standard", workflow_config, dry_run=True)
    mock_run.assert_not_called()


def test_export_all_single_step_writes_job_bundle(config, tmp_path):
    from ASOkai._pipeline.steps.download_genome import DownloadGenomeStep

    export_dir = runner.export_all(
        [DownloadGenomeStep()],
        config,
        outdir=tmp_path,
    )

    job_text = (export_dir / "run.cwl").read_text()
    assert "class: Workflow" in job_text
    assert "step_download_genome:" in job_text
    assert (export_dir / "steps" / "download-genome.cwl").exists()
    job = yaml.safe_load((export_dir / "job.yml").read_text())
    assert job["assembly"] == "GRCh38"
    assert job["source"] == "ensembl"


def test_export_all_writes_runnable_bundle(workflow_config, tmp_path):
    from ASOkai._pipeline.tasks.instantiate_target_gene import InstantiateTargetGeneTask

    export_dir = runner.export_all(
        [InstantiateTargetGeneTask()],
        workflow_config,
        outdir=tmp_path,
        runner_name="cwltool",
    )

    assert export_dir.parent == tmp_path
    assert (export_dir / "run.cwl").exists()
    assert (export_dir / "publish.cwl").exists()
    assert (export_dir / "output-layout.yml").exists()
    assert (export_dir / "steps" / "download-genome.cwl").exists()
    assert (export_dir / "steps" / "create-target-gene.cwl").exists()
    assert (export_dir / "job.yml").exists()
    assert (export_dir / "README.md").exists()
    assert "class: Workflow" in (export_dir / "run.cwl").read_text()
    readme = (export_dir / "README.md").read_text()
    assert "prepared for `cwltool`" in readme
    assert str(export_dir.resolve()) not in readme
    assert "cwltool --outdir /path/to/data run.cwl job.yml" in readme
    assert "Alternative runner" not in readme

    job = yaml.safe_load((export_dir / "job.yml").read_text())
    assert job["assembly"] == "GRCh38"
    assert job["release"] == 114
    assert job["target_id"] == "ENSG00000133703"
    assert "target_gene_output" not in job


def test_export_all_readme_uses_toil_runner(workflow_config, tmp_path):
    from ASOkai._pipeline.tasks.instantiate_target_gene import InstantiateTargetGeneTask

    export_dir = runner.export_all(
        [InstantiateTargetGeneTask()],
        workflow_config,
        outdir=tmp_path,
        runner_name="toil-cwl-runner",
    )

    readme = (export_dir / "README.md").read_text()
    assert "prepared for `toil-cwl-runner`" in readme
    assert str(export_dir.resolve()) not in readme
    assert "toil-cwl-runner --outdir /path/to/data run.cwl job.yml" in readme


def test_executor_from_name_uses_central_runner_configuration():
    assert isinstance(runner.executor_from_name("cwltool"), CwlToolExecutor)
    assert isinstance(runner.executor_from_name("toil"), ToilExecutor)

    with pytest.raises(ValueError, match="Unknown runner 'unknown'"):
        runner.executor_from_name("unknown")


def test_runner_name_from_name_uses_central_runner_configuration():
    assert runner.runner_name_from_name("cwltool") == "cwltool"
    assert runner.runner_name_from_name("toil") == "toil-cwl-runner"


def test_export_all_empty_runnables_raises(workflow_config):
    with pytest.raises(ValueError, match="empty runnables"):
        runner.export_all([], workflow_config)


def test_export_all_includes_steps_even_when_outputs_exist(workflow_config, tmp_path):
    from ASOkai._pipeline.steps.download_genome import DownloadGenomeStep

    step = DownloadGenomeStep()
    for path in step.output_paths(workflow_config).values():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()

    export_dir = runner.export_all([step], workflow_config, outdir=tmp_path)

    assert (export_dir / "run.cwl").exists()
    assert (export_dir / "publish.cwl").exists()
    assert (export_dir / "output-layout.yml").exists()
    assert (export_dir / "steps" / "download-genome.cwl").exists()
    assert "step_download_genome:" in (export_dir / "run.cwl").read_text()


def test_run_task_multistep_dry_run_returns_final_outputs(workflow_config):
    executor = MagicMock()

    result = runner.run_task(
        "instantiate-target-gene",
        workflow_config,
        dry_run=True,
        executor=executor,
    )

    assert result == {
        "target_gene": (
            Path(workflow_config["datadir"])
            / "GRCh38"
            / "targets"
            / "ENSG00000133703"
            / "ENSG00000133703_k16_pre-mrna.json"
        )
    }
    executor.run.assert_not_called()


def test_run_all_empty_runnables_raises(workflow_config):
    with pytest.raises(ValueError, match="empty runnables"):
        runner.run_all([], workflow_config)


def test_run_plan_multistep_dry_run_returns_final_outputs(workflow_config):
    from ASOkai._pipeline.steps.create_target_gene import CreateTargetGeneStep
    from ASOkai._pipeline.steps.download_genome import DownloadGenomeStep

    executor = MagicMock()
    plan = ExecutionPlan(
        steps_to_run=[DownloadGenomeStep(), CreateTargetGeneStep()],
        pre_resolved={},
    )

    result = runner.run_plan(
        plan,
        "instantiate-target-gene",
        workflow_config,
        dry_run=True,
        executor=executor,
    )

    assert result == CreateTargetGeneStep().output_paths(workflow_config)
    executor.run.assert_not_called()


def test_flatten_workflow_expands_task_then_step():
    """A workflow with a Task followed by a Step flattens to their Steps in order."""
    from ASOkai._pipeline.steps.download_genome import DownloadGenomeStep
    from ASOkai._pipeline.steps.create_target_gene import CreateTargetGeneStep

    download = DownloadGenomeStep()
    create = CreateTargetGeneStep()

    class MiniTask:
        name: ClassVar[str] = "mini"
        description: ClassVar[str] = ""
        steps: list[Step] = [download]

        def output_paths(self, config: dict) -> dict[str, Path]:
            return {}

        def outputs_exist(self, config: dict) -> bool:
            return False

        def cleanup(self, config: dict) -> None:
            return None

    class MiniWorkflow:
        name: ClassVar[str] = "mw"
        description: ClassVar[str] = ""
        members: list[Runnable] = [MiniTask(), create]

        def output_paths(self, config: dict) -> dict[str, Path]:
            return {}

        def outputs_exist(self, config: dict) -> bool:
            return False

        def cleanup(self, config: dict) -> None:
            return None

    from ASOkai._pipeline.plan import _flatten_runnable

    objs = _flatten_runnable(MiniWorkflow())
    assert [s.name for s in objs] == ["download-genome", "create-target-gene"]


def test_flatten_workflow_expands_nested_workflow():
    """A workflow containing a nested workflow flattens all steps recursively."""
    from ASOkai._pipeline.steps.download_genome import DownloadGenomeStep
    from ASOkai._pipeline.steps.create_target_gene import CreateTargetGeneStep

    download = DownloadGenomeStep()
    create = CreateTargetGeneStep()

    class Inner:
        name: ClassVar[str] = "inner"
        description: ClassVar[str] = ""
        members: list[Runnable] = [download]

        def output_paths(self, config: dict) -> dict[str, Path]:
            return {}

        def outputs_exist(self, config: dict) -> bool:
            return False

        def cleanup(self, config: dict) -> None:
            return None

    class Outer:
        name: ClassVar[str] = "outer"
        description: ClassVar[str] = ""
        members: list[Runnable] = [Inner(), create]

        def output_paths(self, config: dict) -> dict[str, Path]:
            return {}

        def outputs_exist(self, config: dict) -> bool:
            return False

        def cleanup(self, config: dict) -> None:
            return None

    from ASOkai._pipeline.plan import _flatten_runnable

    objs = _flatten_runnable(Outer())
    assert [s.name for s in objs] == ["download-genome", "create-target-gene"]


def test_flatten_workflow_cycle_raises():
    """A workflow that references itself raises a ValueError."""
    class SelfRef:
        name: ClassVar[str] = "loop"
        description: ClassVar[str] = ""
        members: list[Runnable] = []

        def output_paths(self, config: dict) -> dict[str, Path]:
            return {}

        def outputs_exist(self, config: dict) -> bool:
            return False

        def cleanup(self, config: dict) -> None:
            return None

    w = SelfRef()
    w.members = [w]
    from ASOkai._pipeline.plan import _flatten_runnable

    with pytest.raises(ValueError, match="cycle"):
        _flatten_runnable(w)
