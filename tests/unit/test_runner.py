#!/usr/bin/env python
"""
Filename: tests/unit/test_runner.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Tests for pipeline runner logic.
License: LGPL-3.0-or-later
"""

import logging
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import yaml
from ASOkai.Plugins import (
    FileInput,
    FileOutput,
    Step,
    StepSpec,
)
from ASOkai._pipeline import runner
from ASOkai._cwl.executors import CwlToolExecutor, ToilExecutor
from ASOkai._pipeline.contracts.execution import StepInputBinding, StepRun
from ASOkai._pipeline.plan import build_plan
from ASOkai._pipeline.steps.core.create_target_gene import CreateTargetGeneStep
from ASOkai._pipeline.steps.core.download_genome import DownloadGenomeStep
from ASOkai._pipeline.tasks.instantiate_target_gene import InstantiateTargetGeneTask
from ASOkai._pipeline.workflows.standard import StandardWorkflow


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


def _step_run(step, config):
    return StepRun(
        step.name,
        step,
        config,
        inputs=tuple(
            StepInputBinding(
                file_input,
                Path(config["datadir"]) / "inputs" / file_input.name,
            )
            for file_input in step.spec.inputs
        ),
    )


def _materializing_executor(*filenames, before_run=None):
    executor = MagicMock()

    def run(cwl_path, _job_path, outdir):
        if before_run is not None:
            before_run()
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


def _run_download(config, **kwargs):
    """Run the download step through the generic runner entry point."""
    step = DownloadGenomeStep()
    return runner.run_all(
        [step],
        config,
        registered_steps={step.name: step},
        **kwargs,
    )


def test_runner_skips_execution_when_outputs_exist(config, tmp_path):
    step = DownloadGenomeStep()
    run = _step_run(step, config)
    base = tmp_path / "GRCh38" / "ensembl" / "114" / "genome"
    base.mkdir(parents=True)
    for p in run.output_paths().values():
        p.touch()

    with patch("ASOkai._cwl.executors.CwlToolExecutor.run") as mock_run:
        result = _run_download(config)
        mock_run.assert_not_called()
    assert set(result) == {
        "download-genome.dna",
        "download-genome.cdna",
        "download-genome.annotation",
        "download-genome.db",
    }


def test_dry_run_returns_outputs_without_executing(config):
    with patch("ASOkai._cwl.executors.CwlToolExecutor.run") as execute:
        result = _run_download(
            config,
            dry_run=True,
            force=True,
        )

    execute.assert_not_called()
    assert "download-genome.dna" in result
    assert "download-genome.cdna" in result
    assert "download-genome.annotation" in result


def test_runner_writes_job_bundle_and_reports_outputs(config, tmp_path, caplog):
    executor = _materializing_executor("dna.fa.gz", "cdna.fa.gz", "annotation.gtf.gz", "annotation.db")
    caplog.set_level(logging.INFO)

    _run_download(config, force=True, executor=executor)

    export_dirs = list((tmp_path / "jobs").glob("asokai-job-*"))
    assert len(export_dirs) == 1
    cwl_path, job_path, output_dir = executor.run.call_args.args
    assert cwl_path == export_dirs[0] / "run.cwl"
    assert job_path == export_dirs[0] / "job.yml"
    assert output_dir == tmp_path
    assert (export_dirs[0] / "job.yml").exists()
    assert (export_dirs[0] / "publish.cwl").exists()
    assert (export_dirs[0] / "output-layout.yml").exists()
    assert (export_dirs[0] / "steps" / "download-genome.cwl").exists()
    inputs = yaml.safe_load(job_path.read_text())
    assert inputs["download-genome.assembly"] == "GRCh38"
    paths = _step_run(DownloadGenomeStep(), config).output_paths()
    assert all(paths[name].exists() for name in (
        "dna", "cdna", "annotation", "db"
    ))
    completion = caplog.records[-1].getMessage()
    assert completion.startswith("[download-genome] Completed successfully")
    assert "\nOutputs:\n  dna" in completion
    assert str(paths["dna"]) in completion
    assert f"\nJob bundle: {export_dirs[0]}" in completion


def test_runner_rejects_missing_published_outputs(config):
    executor = _materializing_executor("dna.fa.gz")

    with pytest.raises(RuntimeError, match="did not publish expected output"):
        _run_download(config, force=True, executor=executor)

    paths = _step_run(DownloadGenomeStep(), config).output_paths()
    assert paths["dna"].exists()
    assert not paths["cdna"].exists()


def test_runner_rejects_invalid_published_outputs(config):
    run = _step_run(DownloadGenomeStep(), config)

    with patch.object(
        StepRun,
        "validate_output_files",
        side_effect=ValueError("invalid contents"),
    ):
        with pytest.raises(RuntimeError, match="published invalid output"):
            runner._validate_published_outputs((run,))


def test_runner_rejects_unsupported_download_source(config):
    executor = _materializing_executor("dna.fa.gz", "cdna.fa.gz", "annotation.gtf.gz", "annotation.db")
    config["genome"]["source"] = "ucsc"

    with pytest.raises(ValueError, match=r"genome.source.*ensembl"):
        _run_download(
            config,
            force=True,
            executor=executor,
        )

    executor.run.assert_not_called()


def test_forced_dry_run_does_not_cleanup_outputs(config, tmp_path):
    step = DownloadGenomeStep()
    run = _step_run(step, config)
    base = tmp_path / "GRCh38" / "ensembl" / "114" / "genome"
    base.mkdir(parents=True)
    for p in run.output_paths().values():
        p.touch()

    with patch("ASOkai._cwl.executors.CwlToolExecutor.run"):
        _run_download(config, force=True, dry_run=True)

    assert all(path.exists() for path in run.output_paths().values())


def test_forced_runner_preserves_existing_output_when_execution_fails(config):
    step = DownloadGenomeStep()
    existing_output = _step_run(step, config).output_paths()["dna"]
    existing_output.parent.mkdir(parents=True)
    existing_output.write_text("stale")

    executor = MagicMock()
    executor.runner_name = "test-runner"
    executor.run.side_effect = RuntimeError("execution failed")

    with pytest.raises(RuntimeError, match="execution failed"):
        _run_download(
            config,
            force=True,
            executor=executor,
        )

    assert existing_output.read_text() == "stale"


def test_non_recursive_run_rejects_missing_dependency(config, monkeypatch):
    step = DownloadGenomeStep()

    class MockBuildStep(Step):
        name = "build-genome"
        description = ""
        genome_output = FileOutput(
            "genome",
            destination="genome/genome.txt",
        )
        spec = StepSpec(outputs=[genome_output])

        def cleanup(self, c):
            return None

    monkeypatch.setattr(
        DownloadGenomeStep,
        "spec",
        replace(
            DownloadGenomeStep.spec,
            inputs=[
                FileInput(
                    "genome",
                    source=MockBuildStep.genome_output,
                )
            ],
        ),
    )

    mock_build = MockBuildStep()

    registry = {
        "download-genome": step,
        "build-genome": mock_build,
    }
    with pytest.raises(RuntimeError, match="'build-genome'.*required"):
        runner.run_all(
            [step],
            config,
            non_recursive=True,
            registered_steps=registry,
        )


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
            "k": 16,
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


def test_workflow_dry_run_reports_resources_without_executing(
    workflow_config,
    caplog,
):
    workflow_config["resources"] = {
        "intrinsic-features": {"n_processes": 4},
    }
    caplog.set_level(logging.INFO)

    with patch("ASOkai._cwl.executors.CwlToolExecutor.run") as mock_run:
        runner.run_all(
            [StandardWorkflow()],
            workflow_config,
            dry_run=True,
        )

    mock_run.assert_not_called()
    report = next(
        record.getMessage()
        for record in caplog.records
        if record.getMessage().startswith("[standard] Dry run:")
    )
    assert "[standard] Dry run: 4 steps would execute:" in report
    assert "  4. intrinsic-features" in report
    assert "     Resources:\n       workers: 4" in report


def test_export_all_single_step_writes_job_bundle(config, tmp_path):
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
    assert job["download-genome.assembly"] == "GRCh38"
    assert job["download-genome.source"] == "ensembl"


def test_export_all_writes_runnable_bundle(workflow_config, tmp_path):
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
    assert job["download-genome.assembly"] == "GRCh38"
    assert job["download-genome.release"] == 114
    assert job["create-target-gene.target_id"] == "ENSG00000133703"
    assert "create-target-gene.target_gene_output" not in job


def test_executor_from_name_uses_central_runner_configuration():
    assert isinstance(runner.executor_from_name("cwltool"), CwlToolExecutor)
    assert isinstance(runner.executor_from_name("toil"), ToilExecutor)
    assert runner.executor_from_name("cwltool", verbose=True).verbose is True
    assert runner.executor_from_name("toil", verbose=True).verbose is True

    with pytest.raises(ValueError, match="Unknown runner 'unknown'"):
        runner.executor_from_name("unknown")


def test_runner_executable_from_name_uses_central_runner_configuration():
    assert runner.runner_executable_from_name("cwltool") == "cwltool"
    assert runner.runner_executable_from_name("toil") == "toil-cwl-runner"


def test_export_all_empty_runnables_raises(workflow_config):
    with pytest.raises(ValueError, match="empty runnables"):
        runner.export_all([], workflow_config)


def test_export_all_includes_steps_even_when_outputs_exist(workflow_config, tmp_path):
    step = DownloadGenomeStep()
    for path in _step_run(step, workflow_config).output_paths().values():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()

    export_dir = runner.export_all([step], workflow_config, outdir=tmp_path)

    assert (export_dir / "run.cwl").exists()
    assert (export_dir / "publish.cwl").exists()
    assert (export_dir / "output-layout.yml").exists()
    assert (export_dir / "steps" / "download-genome.cwl").exists()
    assert "step_download_genome:" in (export_dir / "run.cwl").read_text()


def test_export_all_includes_only_goal_steps_by_default(
    workflow_config,
    tmp_path,
):
    download = DownloadGenomeStep()
    create = CreateTargetGeneStep()
    registry = {download.name: download, create.name: create}
    download_run = _step_run(download, workflow_config)
    for path in download_run.output_paths().values():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()

    export_dir = runner.export_all(
        [create],
        workflow_config,
        outdir=tmp_path,
        registered_steps=registry,
    )

    assert (export_dir / "steps" / "create-target-gene.cwl").exists()
    assert not (export_dir / "steps" / "download-genome.cwl").exists()
    job = yaml.safe_load((export_dir / "job.yml").read_text())
    assert job["download-genome.dna"]["path"] == str(
        download_run.output_paths()["dna"].resolve()
    )


def test_recursive_export_includes_complete_producer_closure(
    workflow_config,
    tmp_path,
):
    download = DownloadGenomeStep()
    create = CreateTargetGeneStep()
    registry = {download.name: download, create.name: create}
    for path in _step_run(download, workflow_config).output_paths().values():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()

    export_dir = runner.export_all(
        [create],
        workflow_config,
        recursive=True,
        outdir=tmp_path,
        registered_steps=registry,
    )

    assert (export_dir / "steps" / "download-genome.cwl").exists()
    assert (export_dir / "steps" / "create-target-gene.cwl").exists()
    job = yaml.safe_load((export_dir / "job.yml").read_text())
    assert "download-genome.dna" not in job


def test_export_does_not_require_input_override_to_exist(
    workflow_config,
    tmp_path,
):
    download = DownloadGenomeStep()
    create = CreateTargetGeneStep()
    registry = {download.name: download, create.name: create}
    missing_override = tmp_path / "missing-dna.fa"
    workflow_config["steps"] = {
        create.name: {
            "inputs": {
                "dna": {"path_override": str(missing_override)},
            },
        },
    }

    export_dir = runner.export_all(
        [create],
        workflow_config,
        outdir=tmp_path,
        registered_steps=registry,
    )

    job = yaml.safe_load((export_dir / "job.yml").read_text())
    assert job["create-target-gene.dna"]["path"] == str(
        missing_override.resolve()
    )


def test_task_dry_run_returns_requested_outputs(workflow_config):
    executor = MagicMock()

    result = runner.run_all(
        [InstantiateTargetGeneTask()],
        workflow_config,
        dry_run=True,
        executor=executor,
    )

    assert set(result) == {
        "download-genome.dna",
        "download-genome.cdna",
        "download-genome.annotation",
        "download-genome.db",
        "create-target-gene.target_gene",
    }
    assert result["create-target-gene.target_gene"] == (
        Path(workflow_config["datadir"])
        / "GRCh38"
        / "ensembl"
        / "114"
        / "targets"
        / "ENSG00000133703"
        / "ENSG00000133703_k16_pre-mrna.json"
    )
    executor.run.assert_not_called()


def test_run_all_empty_runnables_raises(workflow_config):
    with pytest.raises(ValueError, match="empty runnables"):
        runner.run_all([], workflow_config)


def test_run_plan_multistep_dry_run_returns_requested_outputs(workflow_config):
    executor = MagicMock()
    download = DownloadGenomeStep()
    create = CreateTargetGeneStep()
    plan = build_plan(
        [create],
        workflow_config,
        _registry={download.name: download, create.name: create},
    )

    result = runner.run_plan(
        plan,
        "instantiate-target-gene",
        workflow_config,
        dry_run=True,
        executor=executor,
    )

    assert result == {
        "create-target-gene.target_gene": plan.goals[0].output_paths()[
            "target_gene"
        ]
    }
    executor.run.assert_not_called()


def test_dry_run_groups_parameters_and_qualified_inputs(workflow_config, caplog):
    download = DownloadGenomeStep()
    create = CreateTargetGeneStep()
    plan = build_plan(
        [create],
        workflow_config,
        _registry={download.name: download, create.name: create},
    )
    caplog.set_level(logging.INFO)

    runner.run_plan(
        plan,
        "instantiate-target-gene",
        workflow_config,
        dry_run=True,
        executor=MagicMock(),
    )

    report = caplog.records[-1].getMessage()
    assert report.startswith(
        "[instantiate-target-gene] Dry run: 2 steps would execute:"
    )
    assert "\n  1. download-genome\n     Parameters:" in report
    assert "       assembly: GRCh38" in report
    assert "target_name" not in report
    assert "\n  2. create-target-gene\n     Parameters:" in report
    assert "     Inputs:" in report
    assert "       dna        <- download-genome.dna" in report
    assert "       annotation <- download-genome.annotation" in report
