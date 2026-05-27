"""Tests for pipeline runner logic."""
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from ASOkai._pipeline import runner
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

    with patch("ASOkai._pipeline.executors.CwlToolExecutor.run") as mock_run:
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
    with patch("ASOkai._pipeline.executors.CwlToolExecutor.run") as mock_run:
        runner.run_step("download-genome", config, dry_run=True, force=True)
        mock_run.assert_not_called()


def test_run_step_uses_injected_executor(config):
    executor = MagicMock()

    runner.run_step("download-genome", config, force=True, executor=executor)

    executor.run.assert_called_once()


def test_run_step_uses_config_download_source(config):
    executor = MagicMock()

    runner.run_step("download-genome", config, force=True, executor=executor)

    _, inputs, _ = executor.run.call_args.args
    assert inputs["source"] == "ensembl"


def test_run_step_uses_configured_download_source(config):
    executor = MagicMock()
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

    with patch("ASOkai._pipeline.executors.CwlToolExecutor.run"):
        runner.run_step("download-genome", config, force=True, dry_run=True)

    assert step.outputs_exist(config) is True


def test_run_step_missing_dependency_raises(config):
    from ASOkai._pipeline.steps.download_genome import DownloadGenomeStep

    step = DownloadGenomeStep()
    step.dependencies = ["build-genome"]

    # build-genome must conform to Step protocol to pass runner validation
    mock_build = MagicMock()
    mock_build.name = "build-genome"
    mock_build.description = ""
    mock_build.cli_module = "tests.fake_step"
    mock_build.dependencies = []
    mock_build.config_map = {}
    mock_build.input_overrides = {}
    mock_build.cwl_path = "/fake/path"
    mock_build.outdir = lambda c: Path(".")
    mock_build.output_paths = lambda c: {}
    mock_build.outputs_exist = lambda c: False
    mock_build.cleanup = lambda c: None

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
    with patch("ASOkai._pipeline.executors.CwlToolExecutor.run") as mock_run:
        runner.run_workflow("standard", workflow_config, dry_run=True)
    mock_run.assert_not_called()


def test_run_task_export_cwl_writes_file_and_skips_executor(workflow_config, tmp_path):
    export_path = tmp_path / "task.cwl"
    executor = MagicMock()

    result = runner.run_task(
        "instantiate-target-gene",
        workflow_config,
        export_cwl=export_path,
        executor=executor,
    )

    assert result is None
    assert export_path.exists()
    assert "class: Workflow" in export_path.read_text()
    executor.run.assert_not_called()


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
        name = "mini"
        description = ""
        steps = [download]

        def output_paths(self, c): return {}
        def outputs_exist(self, c): return False
        def cleanup(self, c): return None

    class MiniWorkflow:
        name = "mw"
        description = ""
        members = [MiniTask(), create]

        def output_paths(self, c): return {}
        def outputs_exist(self, c): return False
        def cleanup(self, c): return None

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
        name = "inner"
        description = ""
        members = [download]

        def output_paths(self, c): return {}
        def outputs_exist(self, c): return False
        def cleanup(self, c): return None

    class Outer:
        name = "outer"
        description = ""
        members = [Inner(), create]

        def output_paths(self, c): return {}
        def outputs_exist(self, c): return False
        def cleanup(self, c): return None

    from ASOkai._pipeline.plan import _flatten_runnable

    objs = _flatten_runnable(Outer())
    assert [s.name for s in objs] == ["download-genome", "create-target-gene"]


def test_flatten_workflow_cycle_raises():
    """A workflow that references itself raises a ValueError."""
    class SelfRef:
        name = "loop"
        description = ""
        members: list = []

        def output_paths(self, c): return {}
        def outputs_exist(self, c): return False
        def cleanup(self, c): return None

    w = SelfRef()
    w.members = [w]
    from ASOkai._pipeline.plan import _flatten_runnable

    with pytest.raises(ValueError, match="cycle"):
        _flatten_runnable(w)
