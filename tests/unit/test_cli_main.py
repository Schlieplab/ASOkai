#!/usr/bin/env python
"""
Filename: tests/unit/test_cli_main.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Tests for the public ASOkai CLI entrypoint.
License: LGPL-3.0-or-later
"""

import logging
from pathlib import Path
from types import SimpleNamespace

import pytest
from click.testing import CliRunner

from ASOkai._logging import active_log_contexts, log_context
from ASOkai._cli.main import main
from ASOkai._cli.options import _CliLogFormatter


def test_cli_logging_shows_module_details_only_in_verbose_mode(caplog):
    formatter = _CliLogFormatter()
    record = logging.LogRecord(
        "ASOkai._pipeline.runner",
        logging.INFO,
        __file__,
        1,
        "Planned execution",
        (),
        None,
    )

    caplog.set_level(logging.INFO)
    assert formatter.format(record) == "Planned execution"

    caplog.set_level(logging.DEBUG)
    assert formatter.format(record) == (
        "INFO ASOkai._pipeline.runner: Planned execution"
    )


def test_cli_logging_prefixes_every_non_empty_line_with_context(caplog):
    formatter = _CliLogFormatter()
    record = logging.LogRecord(
        "ASOkai._pipeline.runner",
        logging.INFO,
        __file__,
        1,
        "First line\n\nSecond line",
        (),
        None,
    )
    caplog.set_level(logging.INFO)

    with log_context("workflow:standard"):
        rendered = formatter.format(record)

    assert rendered == (
        "[workflow:standard] First line\n\n" "[workflow:standard] Second line"
    )


@pytest.mark.parametrize(
    ("arguments", "catalog_getter"),
    [
        (["list", "steps"], "ASOkai._cli.catalog.get_pipeline_catalog"),
        (
            ["describe", "step", "download-genome"],
            "ASOkai._cli.catalog.get_pipeline_catalog",
        ),
        (
            ["run", "--step", "download-genome"],
            "ASOkai._cli.execution.get_pipeline_catalog",
        ),
        (
            ["export", "--step", "download-genome"],
            "ASOkai._cli.execution.get_pipeline_catalog",
        ),
        (["step", "download-genome"], "ASOkai._cli.main.get_steps"),
    ],
)
def test_commands_report_catalog_errors_without_a_traceback(
    monkeypatch,
    arguments,
    catalog_getter,
):
    def reject_catalog():
        raise ValueError("broken catalog")

    monkeypatch.setattr(catalog_getter, reject_catalog)

    result = CliRunner().invoke(main, arguments)

    assert result.exit_code != 0
    assert "Error: broken catalog" in result.output
    assert "Traceback" not in result.output


def test_internal_cwl_commands_are_not_listed_in_help():
    runner = CliRunner()

    result = runner.invoke(main, ["--help"])
    short_result = runner.invoke(main, ["-h"])

    assert result.exit_code == 0
    assert short_result.exit_code == 0
    assert "Usage:" in short_result.output
    assert " step " not in result.output
    assert "publish-outputs" not in result.output


def test_run_help_uses_configfile_and_scoped_run_options():
    runner = CliRunner()

    result = runner.invoke(main, ["run", "--help"])
    short_result = runner.invoke(main, ["run", "-h"])

    assert result.exit_code == 0
    assert short_result.exit_code == 0
    assert "--configfile, --config-file FILE" in short_result.output
    assert "--configfile, --config-file FILE" in result.output
    assert "--executor [toil|cwltool]" in result.output
    assert "--param VALUE" in result.output
    assert "shared PATH=VALUE" in result.output
    assert "--no-config" in result.output
    assert "--config KEY=VALUE" not in result.output
    assert "--non-recursive" in result.output
    assert "--recursive" not in result.output
    assert "--set" not in result.output


def test_export_help_uses_explicit_recursive_option():
    runner = CliRunner()

    result = runner.invoke(main, ["export", "--help"])

    assert result.exit_code == 0
    assert "--recursive" in result.output
    assert "--non-recursive" not in result.output
    assert "--param VALUE" in result.output
    assert "shared PATH=VALUE" in result.output
    assert "--no-config" in result.output
    assert "--config KEY=VALUE" not in result.output


def test_public_subcommands_accept_short_help():
    runner = CliRunner()

    for command in ("list", "describe", "run", "export"):
        result = runner.invoke(main, [command, "-h"])
        assert result.exit_code == 0
        assert "Usage:" in result.output


def test_list_commands_show_registered_units():
    runner = CliRunner()

    steps = runner.invoke(main, ["list", "steps"])
    tasks = runner.invoke(main, ["list", "tasks"])
    analyses = runner.invoke(main, ["list", "analyses"])
    workflows = runner.invoke(main, ["list", "workflows"])

    assert steps.exit_code == 0
    assert "Core\n" in steps.output
    assert "Analysis\n" in steps.output
    assert "download-genome" in steps.output
    assert "Downloads genome DNA" in steps.output
    assert "create-target-gene" in steps.output
    assert "generate-therapeutic-candidates" in steps.output
    assert "compute-intrinsic-features" in steps.output
    assert "target-gene-to-fasta" not in steps.output
    assert "[Per site] Computes nucleotide composition" in steps.output

    assert tasks.exit_code == 0
    assert "Core\n" in tasks.output
    assert "instantiate-target-gene" in tasks.output
    assert "index-target-gene" not in tasks.output
    assert "Downloads genome data" in tasks.output

    assert analyses.exit_code == 0
    assert "compute-intrinsic-features" in analyses.output
    assert "(step)" in analyses.output
    assert "[Per site]" in analyses.output
    assert "instantiate-target-gene" not in analyses.output

    assert workflows.exit_code == 0
    assert "standard" in workflows.output
    assert "Standard pipeline" in workflows.output

    verbose_steps = runner.invoke(main, ["list", "-v", "steps"])
    assert verbose_steps.exit_code == 0
    assert "target-gene-to-fasta" not in verbose_steps.output


def test_list_analyses_includes_categorized_tasks_and_respects_hidden_steps(
    monkeypatch,
):
    from dataclasses import replace

    from ASOkai._pipeline.catalog import get_pipeline_catalog
    from ASOkai._pipeline.contracts.run_spec import RunSpec
    from ASOkai._pipeline.steps.analysis.intrinsic_features import (
        IntrinsicFeaturesStep,
    )
    from ASOkai._pipeline.tasks.base import Task

    class ExampleAnalysisTask(Task):
        name = "example-analysis-task"
        description = "Combines analysis runs."
        category = "analysis"
        runs = (RunSpec("features", IntrinsicFeaturesStep()),)

    class UncategorizedTask(Task):
        name = "uncategorized-task"
        description = "Example plugin task without a category."
        runs = (RunSpec("features", IntrinsicFeaturesStep()),)

    class InternalFeaturesStep(IntrinsicFeaturesStep):
        listed = False

    catalog = get_pipeline_catalog()
    catalog = replace(
        catalog,
        steps={
            **catalog.steps,
            "compute-intrinsic-features": InternalFeaturesStep(),
        },
        tasks={
            **catalog.tasks,
            "example-analysis-task": ExampleAnalysisTask(),
            "uncategorized-task": UncategorizedTask(),
        },
    )
    monkeypatch.setattr("ASOkai._cli.catalog.get_pipeline_catalog", lambda: catalog)
    runner = CliRunner()

    public = runner.invoke(main, ["list", "analyses"])
    verbose = runner.invoke(main, ["list", "-v", "analyses"])
    tasks = runner.invoke(main, ["list", "tasks"])

    assert public.exit_code == verbose.exit_code == 0
    assert "example-analysis-task" in public.output
    assert "(task)" in public.output
    assert "compute-intrinsic-features" not in public.output
    assert "compute-intrinsic-features" in verbose.output
    assert "(step)" in verbose.output
    assert tasks.exit_code == 0
    assert "Analysis\n" in tasks.output
    assert "example-analysis-task" in tasks.output
    assert "Pipeline\n" in tasks.output
    assert "uncategorized-task" in tasks.output


def test_verbose_catalog_reveals_internal_steps(monkeypatch):
    from dataclasses import replace

    from ASOkai._pipeline.catalog import get_pipeline_catalog
    from ASOkai._pipeline.steps.core.download_genome import DownloadGenomeStep

    class InternalDownloadStep(DownloadGenomeStep):
        listed = False

    catalog = get_pipeline_catalog()
    catalog = replace(
        catalog,
        steps={**catalog.steps, "download-genome": InternalDownloadStep()},
    )
    monkeypatch.setattr("ASOkai._cli.catalog.get_pipeline_catalog", lambda: catalog)
    runner = CliRunner()

    public = runner.invoke(main, ["list", "steps"])
    verbose = runner.invoke(main, ["list", "-v", "steps"])
    described = runner.invoke(main, ["describe", "step", "download-genome"])
    verbose_described = runner.invoke(
        main, ["describe", "-v", "step", "download-genome"]
    )

    assert (
        public.exit_code
        == verbose.exit_code
        == described.exit_code
        == verbose_described.exit_code
        == 0
    )
    assert "download-genome" not in public.output
    assert "download-genome" in verbose.output
    assert "Internal\n" in verbose.output
    assert "Type        : Internal" in described.output
    assert "Type        : Internal" in verbose_described.output


def test_describe_step_create_target_gene_shows_details():
    runner = CliRunner()

    result = runner.invoke(main, ["describe", "step", "create-target-gene"])

    assert result.exit_code == 0
    assert "Name        : create-target-gene" in result.output
    assert "Type        : Core" in result.output
    assert "Run parameters:" in result.output
    assert "--param target.target_id=VALUE" in result.output
    assert "--param target.region=VALUE" in result.output
    assert "Inputs:" in result.output
    assert "dna" in result.output
    assert "from download-genome.dna by default" in result.output
    assert "Outputs:" in result.output
    assert "target_gene          JSON" in result.output
    assert "fasta                plain FASTA reference" in result.output
    assert "Input configuration (optional)" not in result.output
    assert "path" not in result.output
    assert "--config " not in result.output
    assert "Dependencies: download-genome" in result.output

    verbose = runner.invoke(main, ["describe", "-v", "step", "create-target-gene"])
    assert verbose.exit_code == 0
    assert "config key: parameters.target.target_id" in verbose.output
    assert "config key: parameters.target.region" in verbose.output
    assert "--input-path dna=PATH" in verbose.output
    assert "steps.create-target-gene.inputs.dna" in verbose.output
    assert "Shared config input:" in verbose.output
    assert "with path: PATH or from: run.ID.OUTPUT" in verbose.output
    assert "Under datadir:" in verbose.output
    assert "{target}_k{k}_{region}.json" in verbose.output


def test_describe_step_without_default_input_explains_file_selection():
    runner = CliRunner()

    result = runner.invoke(main, ["describe", "step", "build-kmc-index"])
    verbose = runner.invoke(main, ["describe", "-v", "step", "build-kmc-index"])

    assert result.exit_code == verbose.exit_code == 0
    assert "reference" in result.output
    assert "supply a file or link a run" in result.output
    assert "kmc_index" in result.output
    assert "KFF k-mer index" in result.output
    assert "--from-run reference=RUN_ID.OUTPUT" in verbose.output
    assert "--input-path reference=PATH" in verbose.output
    assert "steps.build-kmc-index.inputs.reference" in verbose.output
    assert "with path: PATH or from: run.ID.OUTPUT" in verbose.output


def test_describe_step_uses_stepspec_not_step_argparse(monkeypatch):
    from ASOkai._pipeline.steps.core.create_target_gene import (
        CreateTargetGeneStep,
    )

    def unexpected_parser(*args, **kwargs):
        raise AssertionError("unexpected parser lookup")

    monkeypatch.setattr(CreateTargetGeneStep, "build_parser", unexpected_parser)

    runner = CliRunner()
    result = runner.invoke(main, ["describe", "step", "create-target-gene"])

    assert result.exit_code == 0
    assert "pre-mrna" in result.output
    assert "Ensembl gene ID" in result.output


def test_describe_task_expands_step_names():
    runner = CliRunner()

    result = runner.invoke(main, ["describe", "task", "instantiate-target-gene"])

    assert result.exit_code == 0
    assert "Name        : instantiate-target-gene" in result.output
    assert "Steps       : download-genome, create-target-gene" in result.output
    assert "Inputs: (none at task boundary)" in result.output
    assert "Outputs:" in result.output
    assert "target_gene" in result.output
    assert "gene.target_gene" in result.output
    assert "CWL         : (CLI collection; export creates run.cwl)" in result.output
    assert "Steps: download-genome, create-target-gene" not in result.output


def test_describe_workflow_shows_members_and_expanded_steps():
    runner = CliRunner()

    result = runner.invoke(main, ["describe", "workflow", "standard"])

    assert result.exit_code == 0
    assert "Name        : standard" in result.output
    assert (
        "Members     : instantiate-target-gene, generate-therapeutic-candidates, "
        "compute-intrinsic-features" in result.output
    )
    assert "CWL         : (CLI collection; export creates run.cwl)" in result.output
    assert (
        "Steps (expanded): download-genome, create-target-gene, "
        "generate-therapeutic-candidates, compute-intrinsic-features" in result.output
    )


def test_verbose_describe_step_shows_dependency_tree():
    runner = CliRunner()

    result = runner.invoke(
        main, ["describe", "--verbose", "step", "compute-intrinsic-features"]
    )

    assert result.exit_code == 0
    assert "Type        : Analysis" in result.output
    assert "Description : [Per site] Computes nucleotide composition" in result.output
    assert "Dependencies:" in result.output
    assert "`-- create-target-gene" in result.output
    assert "`-- download-genome" in result.output


@pytest.mark.parametrize("command", ["run", "export"])
def test_execution_commands_reject_removed_global_config_option(command):
    result = CliRunner().invoke(
        main,
        [command, "--step", "download-genome", "--config", "parameters.target.k=20"],
    )

    assert result.exit_code != 0
    assert "No such option" in result.output
    assert "--config" in result.output


def test_run_requires_explicit_runnable_selection():
    runner = CliRunner()
    result = runner.invoke(main, ["run"])

    assert result.exit_code != 0
    assert "Select at least one runnable" in result.output


def test_run_accepts_configured_runs_without_cli_selection(monkeypatch, tmp_path):
    captured = {}
    monkeypatch.setattr(
        "ASOkai._cli.execution.cfg.load",
        lambda _path, **_kwargs: {
            "datadir": str(tmp_path),
            "runs": [{"step": "download-genome"}],
        },
    )
    monkeypatch.setattr(
        "ASOkai._cli.execution.runner.run_all",
        lambda runnables, config, **kwargs: captured.update(
            runnables=runnables, config=config, **kwargs
        ),
    )

    result = CliRunner().invoke(main, ["run"])

    assert result.exit_code == 0
    assert captured["runnables"] == []
    assert captured["config"]["runs"] == [{"step": "download-genome"}]
    assert "download-genome" in captured["registered_steps"]


def test_run_dry_run_reads_configured_runs_from_yaml(tmp_path, caplog):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        f"datadir: {tmp_path}\n"
        "parameters:\n"
        "  genome:\n"
        "    assembly: GRCh38\n"
        "    release: 114\n"
        "    species: Homo_sapiens\n"
        "runs:\n"
        "  - step: download-genome\n"
    )

    caplog.set_level(logging.INFO)
    result = CliRunner().invoke(
        main,
        ["run", "--configfile", str(config_file), "--dry-run"],
    )

    assert result.exit_code == 0
    assert any("download-genome" in record.message for record in caplog.records)


def test_run_dry_run_resolves_cli_run_through_yaml_planner(tmp_path, caplog):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        f"datadir: {tmp_path}\n"
        "parameters:\n"
        "  genome:\n"
        "    assembly: GRCh38\n"
        "    release: 114\n"
        "    species: Homo_sapiens\n",
        encoding="utf-8",
    )

    caplog.set_level(logging.INFO)
    result = CliRunner().invoke(
        main,
        [
            "run",
            "--configfile",
            str(config_file),
            "--step",
            "download-genome",
            "--id",
            "genome",
            "--param",
            "genome.release=115",
            "--dry-run",
        ],
    )

    assert result.exit_code == 0, result.output
    assert any("download-genome" in record.message for record in caplog.records)


def test_run_workflow_selects_standard_explicitly(monkeypatch):
    captured = {}

    monkeypatch.setattr("ASOkai._cli.execution.cfg.load", lambda _path, **_kwargs: {})
    monkeypatch.setattr(
        "ASOkai._cli.execution.runner.run_all",
        lambda runnables, config, **kwargs: captured.update(
            runnables=runnables,
            config=config,
            **kwargs,
        ),
    )

    runner = CliRunner()
    result = runner.invoke(main, ["run", "--workflow", "standard"])

    assert result.exit_code == 0
    assert captured["runnables"] == []
    assert captured["config"]["runs"] == [
        {"task": "instantiate-target-gene", "id": "instantiate-target-gene"},
        {"step": "generate-therapeutic-candidates", "id": "generate-therapeutic-candidates"},
        {"step": "compute-intrinsic-features", "id": "compute-intrinsic-features"},
    ]
    assert captured["executor"].__class__.__name__ == "CwlToolExecutor"


def test_run_steps_accepts_repeated_flags(monkeypatch):
    captured = {}

    monkeypatch.setattr("ASOkai._cli.execution.cfg.load", lambda _path, **_kwargs: {})
    monkeypatch.setattr(
        "ASOkai._cli.execution.runner.run_all",
        lambda runnables, config, **kwargs: captured.update(
            runnables=runnables, config=config
        ),
    )

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "run",
            "--step",
            "download-genome",
            "--step",
            "create-target-gene",
        ],
    )

    assert result.exit_code == 0
    assert captured["runnables"] == []
    assert captured["config"]["runs"] == [
        {"step": "download-genome", "id": "download-genome"},
        {"step": "create-target-gene", "id": "create-target-gene"},
    ]


def test_repeated_unnamed_steps_receive_readable_ids(monkeypatch):
    captured = {}
    monkeypatch.setattr("ASOkai._cli.execution.cfg.load", lambda _path: {})
    monkeypatch.setattr(
        "ASOkai._cli.execution.runner.run_all",
        lambda _runnables, config, **_kwargs: captured.update(config=config),
    )

    result = CliRunner().invoke(
        main,
        [
            "run",
            "--step",
            "create-target-gene",
            "--id",
            "testing",
            "--step",
            "compute-intrinsic-features",
            "--from-run",
            "target_gene=testing.target_gene",
            "--step",
            "compute-intrinsic-features",
        ],
    )

    assert result.exit_code == 0, result.output
    assert [run["id"] for run in captured["config"]["runs"]] == [
        "testing",
        "compute-intrinsic-features",
        "compute-intrinsic-features-2",
    ]


def test_run_resolves_task_selection(monkeypatch):
    captured = {}

    monkeypatch.setattr("ASOkai._cli.execution.cfg.load", lambda _path, **_kwargs: {})
    monkeypatch.setattr(
        "ASOkai._cli.execution.runner.run_all",
        lambda runnables, config, **kwargs: captured.update(
            runnables=runnables, config=config
        ),
    )

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["run", "--task", "instantiate-target-gene"],
    )

    assert result.exit_code == 0
    assert captured["runnables"] == []
    assert captured["config"]["runs"] == [
        {"task": "instantiate-target-gene", "id": "instantiate-target-gene"}
    ]


@pytest.mark.parametrize("command", ["run", "export"])
def test_cli_run_options_match_ordered_yaml_declarations(
    monkeypatch, tmp_path, command
):
    from ASOkai._pipeline.contracts.run_spec import RunSpec
    from ASOkai._pipeline.steps.core.create_target_gene import CreateTargetGeneStep
    from ASOkai._pipeline.steps.core.generate_therapeutic_candidates import (
        GenerateTherapeuticCandidatesStep,
    )

    captured = {}
    target_step = CreateTargetGeneStep()
    catalog = SimpleNamespace(
        steps={
            "create-target-gene": target_step,
            "generate-therapeutic-candidates": GenerateTherapeuticCandidatesStep(),
        },
        tasks={
            "compare-regions": SimpleNamespace(
                runs=(RunSpec("transcriptomic", target_step),)
            )
        },
        workflows={},
        config_schema_paths={},
    )
    monkeypatch.setattr("ASOkai._cli.execution.get_pipeline_catalog", lambda: catalog)
    monkeypatch.setattr(
        "ASOkai._cli.execution.cfg.load",
        lambda _path: {"datadir": str(tmp_path), "parameters": {"target": {"k": 16}}},
    )
    monkeypatch.setattr(
        "ASOkai._cli.execution.runner.run_all",
        lambda runnables, config, **_kwargs: captured.update(
            runnables=runnables, config=config
        ),
    )
    monkeypatch.setattr(
        "ASOkai._cli.execution.runner.export_all",
        lambda runnables, config, **_kwargs: captured.update(
            runnables=runnables, config=config
        )
        or tmp_path / "export",
    )

    result = CliRunner().invoke(
        main,
        [
            command,
            "--configfile",
            str(tmp_path / "common.yaml"),
            "--step",
            "create-target-gene",
            "--id",
            "reference-gene",
            "--param",
            "target.region=pre-mrna",
            "--step",
            "generate-therapeutic-candidates",
            "--id",
            "candidates",
            "--from-run",
            "target_gene=reference-gene.target_gene",
            "--task",
            "compare-regions",
            "--id",
            "comparison",
            "--param",
            "target.k=21",
            "--child",
            "transcriptomic",
            "--param",
            "target.k=18",
        ],
    )

    assert result.exit_code == 0, result.output
    assert captured["runnables"] == []
    assert captured["config"]["parameters"]["target"] == {"k": 16}
    assert captured["config"]["runs"] == [
        {
            "step": "create-target-gene",
            "id": "reference-gene",
            "parameters": {"region": "pre-mrna"},
        },
        {
            "step": "generate-therapeutic-candidates",
            "id": "candidates",
            "inputs": {"target_gene": {"from": "run.reference-gene.target_gene"}},
        },
        {
            "task": "compare-regions",
            "id": "comparison",
            "parameters": {"target.k": 21},
            "runs": [{"id": "transcriptomic", "parameters": {"k": 18}}],
        },
    ]


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (["--param", "k=21"], "shared parameter path"),
        (["--id", "gene"], "must follow --step or --task"),
        (
            ["--task", "instantiate-target-gene", "--from-run", "dna=gene.dna"],
            "requires --child",
        ),
        (["--step", "download-genome", "--child", "gene"], "must follow a task"),
        (
            [
                "--step", "download-genome", "--param", "genome.release=21",
                "--param", "genome.release=18",
            ],
            "Duplicate --param",
        ),
    ],
)
def test_cli_rejects_misplaced_run_options(args, message):
    result = CliRunner().invoke(main, ["run", *args])

    assert result.exit_code != 0
    assert message in result.output


@pytest.mark.parametrize("command", ["run", "export"])
def test_cli_only_selection_uses_shared_and_scoped_parameters(
    monkeypatch, tmp_path, command
):
    captured = {}
    monkeypatch.setattr(
        "ASOkai._cli.execution.runner.run_all",
        lambda _runnables, config, **_kwargs: captured.update(config=config),
    )
    monkeypatch.setattr(
        "ASOkai._cli.execution.runner.export_all",
        lambda _runnables, config, **_kwargs: captured.update(config=config)
        or tmp_path / "export",
    )

    with CliRunner().isolated_filesystem(temp_dir=tmp_path):
        # Explicit CLI-only mode ignores an existing default config file.
        Path("config.yaml").write_text(
            "runs:\n  - step: download-genome\n", encoding="utf-8"
        )
        result = CliRunner().invoke(
            main,
            [
                command,
                "--no-config",
                "--param",
                "genome.assembly=GRCh39",
                "--param",
                "genome.release=115",
                "--step",
                "create-target-gene",
                "--param",
                "target.target_id=ENSG00000133703",
            ],
        )

    assert result.exit_code == 0, result.output
    assert captured["config"] == {
        "datadir": "./data",
        "parameters": {"genome": {"assembly": "GRCh39", "release": 115}},
        "runs": [
            {
                "step": "create-target-gene",
                "id": "create-target-gene",
                "parameters": {"target_id": "ENSG00000133703"},
            }
        ],
    }


def test_shared_cli_parameter_overrides_config_and_scoped_parameter(
    monkeypatch, tmp_path
):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        f"datadir: {tmp_path}\n"
        "parameters:\n"
        "  genome:\n"
        "    assembly: GRCh38\n"
        "  target:\n"
        "    region: exonic\n",
        encoding="utf-8",
    )
    captured = {}
    monkeypatch.setattr(
        "ASOkai._cli.execution.runner.run_all",
        lambda _runnables, config, **_kwargs: captured.update(config=config),
    )

    result = CliRunner().invoke(
        main,
        [
            "run",
            "--configfile",
            str(config_path),
            "--param",
            "genome.assembly=GRCh39",
            "--param",
            "target.region=pre-mrna",
            "--step",
            "create-target-gene",
            "--param",
            "target.region=transcriptomic",
        ],
    )

    assert result.exit_code == 0, result.output
    assert captured["config"]["parameters"] == {
        "genome": {"assembly": "GRCh39"},
        "target": {"region": "pre-mrna"},
    }
    assert captured["config"]["runs"] == [
        {
            "step": "create-target-gene",
            "id": "create-target-gene",
            "parameters": {"region": "transcriptomic"},
        }
    ]


@pytest.mark.parametrize("scoped", [False, True])
def test_linked_analysis_uses_target_k_from_selected_producer(
    monkeypatch, tmp_path, scoped
):
    from ASOkai._pipeline.plan import build_export_plan

    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        f"datadir: {tmp_path}\n"
        "parameters:\n"
        "  genome:\n"
        "    assembly: GRCh38\n"
        "    release: 114\n"
        "    species: Homo_sapiens\n"
        "  target:\n"
        "    target_id: ENSG00000133703\n"
        "    k: 16\n"
        "    region: pre-mrna\n",
        encoding="utf-8",
    )
    captured = {}

    def capture_plan(_runnables, config, **kwargs):
        captured["config"] = config
        captured["plan"] = build_export_plan(
            [],
            config,
            recursive=True,
            _registry=kwargs["registered_steps"],
            _tasks=kwargs["registered_tasks"],
            _config_schema_paths=kwargs["config_schema_paths"],
        )

    monkeypatch.setattr("ASOkai._cli.execution.runner.run_all", capture_plan)
    arguments = ["run", "--configfile", str(config_path)]
    if not scoped:
        arguments.extend(["--param", "target.k=18"])
    arguments.extend(["--step", "create-target-gene", "--id", "testing"])
    if scoped:
        arguments.extend(["--param", "target.k=18"])
    arguments.extend(
        [
            "--step",
            "compute-intrinsic-features",
            "--from-run",
            "target_gene=testing.target_gene",
        ]
    )

    result = CliRunner().invoke(main, arguments)

    assert result.exit_code == 0, result.output
    producer, analysis = captured["plan"].goals
    assert producer.parameters["k"] == 18
    assert analysis.config["parameters"]["target"]["k"] == 18
    assert producer.output_paths()["target_gene"].name.endswith("_k18_pre-mrna.json")
    assert analysis.output_paths()["intrinsic_features"].name.endswith(
        "_k18_pre-mrna_intrinsic_all.csv"
    )
    assert captured["config"]["parameters"]["target"]["k"] == (
        16 if scoped else 18
    )


def test_scoped_param_rejects_short_name():
    result = CliRunner().invoke(
        main, ["run", "--step", "create-target-gene", "--param", "k=18"]
    )

    assert result.exit_code != 0
    assert "Unknown parameter path(s): k" in result.output


def test_cli_only_dry_run_passes_shared_values_to_implicit_producer(tmp_path, caplog):
    with CliRunner().isolated_filesystem(temp_dir=tmp_path):
        result = CliRunner().invoke(
            main,
            [
                "run",
                "--dry-run",
                "--param",
                "genome.assembly=GRCh39",
                "--param",
                "genome.release=115",
                "--param",
                "genome.species=Homo_sapiens",
                "--step",
                "create-target-gene",
                "--param",
                "target.target_id=ENSG00000133703",
                "--param",
                "target.k=20",
                "--param",
                "target.region=transcriptomic",
            ],
        )

    assert result.exit_code == 0, result.output
    plan_log = "\n".join(record.message for record in caplog.records)
    assert "download-genome" in plan_log
    assert "assembly: GRCh39" in plan_log
    assert "release: 115" in plan_log
    assert "create-target-gene" in plan_log


def test_cli_step_selection_reads_default_config_for_implicit_producers(
    tmp_path, caplog
):
    with CliRunner().isolated_filesystem(temp_dir=tmp_path):
        Path("config.yaml").write_text(
            "datadir: ./data\n"
            "parameters:\n"
            "  genome:\n"
            "    assembly: GRCh38\n"
            "    release: 114\n"
            "    species: Homo_sapiens\n"
            "  target:\n"
            "    target_id: ENSG00000133703\n"
            "    k: 16\n"
            "    region: pre-mrna\n",
            encoding="utf-8",
        )
        result = CliRunner().invoke(
            main, ["run", "--step", "compute-intrinsic-features", "--dry-run"]
        )

    assert result.exit_code == 0, result.output
    plan_log = "\n".join(record.message for record in caplog.records)
    assert "Dry run: 3 steps would execute" in plan_log
    assert "download-genome" in plan_log
    assert "create-target-gene" in plan_log
    assert "compute-intrinsic-features" in plan_log
    assert "assembly: GRCh38" in plan_log


def test_no_config_rejects_explicit_configfile(tmp_path):
    result = CliRunner().invoke(
        main,
        [
            "run",
            "--no-config",
            "--configfile",
            str(tmp_path / "config.yaml"),
            "--step",
            "download-genome",
        ],
    )

    assert result.exit_code != 0
    assert "--no-config cannot be combined with --configfile" in result.output


def test_explicit_missing_configfile_is_not_treated_as_cli_only(tmp_path):
    result = CliRunner().invoke(
        main,
        [
            "run",
            "--configfile",
            str(tmp_path / "missing.yaml"),
            "--step",
            "download-genome",
        ],
    )

    assert result.exit_code != 0
    assert "missing.yaml" in result.output


def test_cli_preserves_mixed_selection_order_and_file_input(monkeypatch, tmp_path):
    captured = {}
    monkeypatch.setattr("ASOkai._cli.execution.cfg.load", lambda _path: {})
    monkeypatch.setattr(
        "ASOkai._cli.execution.runner.run_all",
        lambda _runnables, config, **_kwargs: captured.update(config=config),
    )

    result = CliRunner().invoke(
        main,
        [
            "run",
            "--task",
            "instantiate-target-gene",
            "--param",
            "target.k=21",
            "--step",
            "create-target-gene",
            "--id",
            "custom",
            "--input-path",
            f"dna={tmp_path / 'genome.fa'}",
            "--step",
            "download-genome",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "parameters" not in captured["config"]
    assert captured["config"]["runs"] == [
        {
            "task": "instantiate-target-gene",
            "id": "instantiate-target-gene",
            "parameters": {"target.k": 21},
        },
        {
            "step": "create-target-gene",
            "id": "custom",
            "inputs": {"dna": {"path": str(tmp_path / "genome.fa")}},
        },
        {"step": "download-genome", "id": "download-genome"},
    ]


def test_cli_rejects_selection_alongside_configured_runs(monkeypatch):
    monkeypatch.setattr(
        "ASOkai._cli.execution.cfg.load",
        lambda _path: {"runs": [{"step": "download-genome"}]},
    )

    result = CliRunner().invoke(
        main,
        ["run", "--configfile", "config.yaml", "--step", "create-target-gene"],
    )

    assert result.exit_code != 0
    assert "not both" in result.output


def test_run_uses_toil_executor_when_requested(monkeypatch):
    captured = {}

    monkeypatch.setattr("ASOkai._cli.execution.cfg.load", lambda _path, **_kwargs: {})
    monkeypatch.setattr(
        "ASOkai._cli.execution.runner.run_all",
        lambda runnables, config, **kwargs: captured.update(kwargs),
    )

    runner = CliRunner()
    result = runner.invoke(
        main, ["run", "--step", "download-genome", "--executor", "toil"]
    )

    assert result.exit_code == 0
    assert captured["executor"].__class__.__name__ == "ToilExecutor"


def test_run_passes_verbose_mode_to_the_executor(monkeypatch):
    captured = {}

    monkeypatch.setattr("ASOkai._cli.execution.cfg.load", lambda _path, **_kwargs: {})
    monkeypatch.setattr(
        "ASOkai._cli.execution.runner.run_all",
        lambda runnables, config, **kwargs: captured.update(kwargs),
    )

    result = CliRunner().invoke(
        main,
        ["run", "--verbose", "--step", "download-genome"],
    )

    assert result.exit_code == 0
    assert captured["executor"].verbose is True


def test_export_steps_uses_outdir_and_runner_name(monkeypatch, tmp_path):
    captured = {}

    monkeypatch.setattr(
        "ASOkai._cli.execution.cfg.load",
        lambda _path, **_kwargs: {"datadir": str(tmp_path / "data")},
    )
    monkeypatch.setattr(
        "ASOkai._cli.execution.runner.export_all",
        lambda runnables, config, **kwargs: captured.update(
            runnables=runnables,
            config=config,
            **kwargs,
        )
        or tmp_path / "exports" / "asokai-export-1",
    )

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "export",
            "--step",
            "download-genome",
            "--step",
            "create-target-gene",
            "--outdir",
            str(tmp_path / "exports"),
            "--executor",
            "toil",
        ],
    )

    assert result.exit_code == 0
    assert captured["runnables"] == []
    assert captured["config"]["runs"] == [
        {"step": "download-genome", "id": "download-genome"},
        {"step": "create-target-gene", "id": "create-target-gene"},
    ]
    assert captured["outdir"] == tmp_path / "exports"
    assert captured["runner_name"] == "toil-cwl-runner"
    assert "CWL export bundle written" in result.output


def test_export_workflow_defaults_outdir_to_none_for_runner(monkeypatch, tmp_path):
    captured = {}

    monkeypatch.setattr(
        "ASOkai._cli.execution.cfg.load",
        lambda _path, **_kwargs: {"datadir": str(tmp_path / "data")},
    )
    monkeypatch.setattr(
        "ASOkai._cli.execution.runner.export_all",
        lambda runnables, config, **kwargs: captured.update(
            runnables=runnables,
            config=config,
            **kwargs,
        )
        or tmp_path / "data" / "jobs" / "asokai-export-1",
    )

    runner = CliRunner()
    result = runner.invoke(main, ["export", "--workflow", "standard"])

    assert result.exit_code == 0
    assert captured["runnables"] == []
    assert captured["config"]["runs"] == [
        {"task": "instantiate-target-gene", "id": "instantiate-target-gene"},
        {"step": "generate-therapeutic-candidates", "id": "generate-therapeutic-candidates"},
        {"step": "compute-intrinsic-features", "id": "compute-intrinsic-features"},
    ]
    assert captured["outdir"] is None
    assert captured["recursive"] is False


def test_export_recursive_flag_is_forwarded(monkeypatch, tmp_path):
    captured = {}
    monkeypatch.setattr(
        "ASOkai._cli.execution.cfg.load",
        lambda _path, **_kwargs: {"datadir": str(tmp_path / "data")},
    )
    monkeypatch.setattr(
        "ASOkai._cli.execution.runner.export_all",
        lambda runnables, config, **kwargs: captured.update(kwargs)
        or tmp_path / "export",
    )

    result = CliRunner().invoke(
        main,
        ["export", "--step", "create-target-gene", "--recursive"],
    )

    assert result.exit_code == 0
    assert captured["recursive"] is True


def test_export_tasks_resolves_task_selection(monkeypatch, tmp_path):
    captured = {}

    monkeypatch.setattr(
        "ASOkai._cli.execution.cfg.load",
        lambda _path, **_kwargs: {"datadir": str(tmp_path / "data")},
    )
    monkeypatch.setattr(
        "ASOkai._cli.execution.runner.export_all",
        lambda runnables, config, **kwargs: captured.update(
            runnables=runnables,
            config=config,
            **kwargs,
        )
        or tmp_path / "data" / "jobs" / "asokai-export-1",
    )

    runner = CliRunner()
    result = runner.invoke(main, ["export", "--task", "instantiate-target-gene"])

    assert result.exit_code == 0
    assert captured["runnables"] == []
    assert captured["config"]["runs"] == [
        {"task": "instantiate-target-gene", "id": "instantiate-target-gene"}
    ]


def test_export_accepts_configured_runs_without_cli_selection(monkeypatch, tmp_path):
    captured = {}
    monkeypatch.setattr(
        "ASOkai._cli.execution.cfg.load",
        lambda _path, **_kwargs: {
            "datadir": str(tmp_path),
            "runs": [{"task": "instantiate-target-gene"}],
        },
    )
    monkeypatch.setattr(
        "ASOkai._cli.execution.runner.export_all",
        lambda runnables, config, **kwargs: captured.update(
            runnables=runnables, config=config, **kwargs
        )
        or tmp_path / "export",
    )

    result = CliRunner().invoke(main, ["export"])

    assert result.exit_code == 0
    assert captured["runnables"] == []
    assert captured["config"]["runs"] == [{"task": "instantiate-target-gene"}]
    assert "instantiate-target-gene" in captured["registered_tasks"]


@pytest.mark.parametrize(
    ("option", "name", "kind"),
    [
        ("--step", "not-a-step", "step"),
        ("--task", "not-a-task", "task"),
        ("--workflow", "not-a-workflow", "workflow"),
    ],
)
def test_run_rejects_unknown_runnables(option, name, kind):
    result = CliRunner().invoke(main, ["run", option, name])

    assert result.exit_code != 0
    assert f"Unknown {kind} '{name}'." in result.output


def test_run_param_rejects_malformed_override(monkeypatch):
    monkeypatch.setattr("ASOkai._cli.execution.cfg.load", lambda _path, **_kwargs: {})

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "run",
            "--step",
            "download-genome",
            "--param",
            "k",
        ],
    )

    assert result.exit_code != 0
    assert "Expected NAME=VALUE" in result.output


def test_run_param_reports_invalid_yaml_value(monkeypatch):
    monkeypatch.setattr("ASOkai._cli.execution.cfg.load", lambda _path: {})

    result = CliRunner().invoke(
        main,
        [
            "run",
            "--step",
            "download-genome",
            "--param",
            "k=[",
        ],
    )

    assert result.exit_code != 0
    assert "Invalid value for --param" in result.output
    assert "Invalid YAML value" in result.output


def test_run_keeps_shared_config_when_selecting_cli_runs(monkeypatch, tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "datadir: .\n" "parameters:\n" "  genome:\n" "    source: ''\n",
        encoding="utf-8",
    )
    captured = {}
    monkeypatch.setattr(
        "ASOkai._cli.execution.runner.run_all",
        lambda runnables, config, **kwargs: captured.update(config=config),
    )

    result = CliRunner().invoke(
        main,
        [
            "run",
            "--step",
            "download-genome",
            "--configfile",
            str(config_path),
        ],
    )

    assert result.exit_code == 0
    assert captured["config"]["parameters"]["genome"]["source"] == ""
    assert captured["config"]["runs"] == [
        {"step": "download-genome", "id": "download-genome"}
    ]


def test_run_displays_configuration_errors_without_traceback(monkeypatch):
    monkeypatch.setattr(
        "ASOkai._cli.execution.cfg.load",
        lambda _path, **_kwargs: {"datadir": "./data"},
    )

    def reject_config(*args, **kwargs):
        raise ValueError(
            "Invalid configuration:\n- $.parameters.target.k: 0 is less than 1"
        )

    monkeypatch.setattr(
        "ASOkai._cli.execution.runner.run_all",
        reject_config,
    )

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["run", "--step", "download-genome"],
    )

    assert result.exit_code != 0
    assert "Error: Invalid configuration:" in result.output
    assert "$.parameters.target.k" in result.output
    assert "Traceback" not in result.output


def test_run_displays_missing_dependency_errors_without_traceback(monkeypatch):
    monkeypatch.setattr(
        "ASOkai._cli.execution.cfg.load",
        lambda _path, **_kwargs: {"datadir": "./data"},
    )

    def reject_plan(*args, **kwargs):
        raise RuntimeError(
            "Step 'download-genome' is required, but its outputs are missing."
        )

    monkeypatch.setattr(
        "ASOkai._cli.execution.runner.run_all",
        reject_plan,
    )

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["run", "--step", "create-target-gene", "--non-recursive"],
    )

    assert result.exit_code != 0
    assert "Error: Step 'download-genome' is required" in result.output
    assert "Traceback" not in result.output


def test_export_displays_configuration_errors_without_traceback(monkeypatch):
    monkeypatch.setattr(
        "ASOkai._cli.execution.cfg.load",
        lambda _path, **_kwargs: {"datadir": "./data"},
    )

    def reject_config(*args, **kwargs):
        raise ValueError(
            "Invalid configuration:\n- $.parameters.target.region: invalid"
        )

    monkeypatch.setattr(
        "ASOkai._cli.execution.runner.export_all",
        reject_config,
    )

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["export", "--step", "download-genome"],
    )

    assert result.exit_code != 0
    assert "Error: Invalid configuration:" in result.output
    assert "$.parameters.target.region" in result.output
    assert "Traceback" not in result.output


def test_run_param_preserves_yaml_scalar_types(monkeypatch):
    captured = {}

    monkeypatch.setattr(
        "ASOkai._cli.execution.cfg.load",
        lambda _path, **_kwargs: {"parameters": {"target": {}}},
    )
    monkeypatch.setattr(
        "ASOkai._cli.execution.runner.run_all",
        lambda runnables, config, **kwargs: captured.update(config=config),
    )

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "run",
            "--step",
            "build-kmc-index",
            "--param",
            "target.k=20",
            "--param",
            "kmc.sm=true",
            "--param",
            "kmc.p=null",
        ],
    )

    assert result.exit_code == 0
    assert captured["config"]["runs"] == [
        {
            "step": "build-kmc-index",
            "id": "build-kmc-index",
            "parameters": {"k": 20, "sm": True, "p": None},
        }
    ]


def test_step_command_dispatches_to_builtin_step(monkeypatch):
    from ASOkai._pipeline.steps.core.download_genome import DownloadGenomeStep

    received: dict[str, object] = {}

    def fake_run_cli(self, argv: list[str] | None = None) -> int:
        received["argv"] = argv
        received["log_contexts"] = active_log_contexts()
        return 0

    monkeypatch.setattr(DownloadGenomeStep, "run_cli", fake_run_cli)

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["step", "download-genome", "--assembly", "GRCh38", "--release", "114"],
    )

    assert result.exit_code == 0
    assert received["argv"] == ["--assembly", "GRCh38", "--release", "114"]
    assert received["log_contexts"] == ("step:download-genome",)
    assert active_log_contexts() == ()


def test_step_command_verbose_enables_debug_logging(monkeypatch):
    from ASOkai._pipeline.steps.core.download_genome import DownloadGenomeStep

    observed: dict[str, object] = {}

    def fake_run_cli(self, argv: list[str] | None = None) -> int:
        observed["debug"] = logging.getLogger().isEnabledFor(logging.DEBUG)
        observed["argv"] = argv
        return 0

    monkeypatch.setattr(DownloadGenomeStep, "run_cli", fake_run_cli)
    root_logger = logging.getLogger()
    previous_level = root_logger.level
    try:
        result = CliRunner().invoke(
            main,
            ["step", "--verbose", "download-genome", "--assembly", "GRCh38"],
        )
    finally:
        root_logger.setLevel(previous_level)

    assert result.exit_code == 0
    assert observed == {"debug": True, "argv": ["--assembly", "GRCh38"]}


def test_step_command_labels_logs_with_run_id(monkeypatch):
    from ASOkai._pipeline.steps.core.download_genome import DownloadGenomeStep

    received: dict[str, object] = {}

    def fake_run_cli(self, argv: list[str] | None = None) -> int:
        received["argv"] = argv
        received["log_contexts"] = active_log_contexts()
        return 0

    monkeypatch.setattr(DownloadGenomeStep, "run_cli", fake_run_cli)

    result = CliRunner().invoke(
        main,
        [
            "step", "--run-id", "runs.download-genome-2", "download-genome",
            "--assembly", "GRCh38",
        ],
    )

    assert result.exit_code == 0
    assert received["argv"] == ["--assembly", "GRCh38"]
    assert received["log_contexts"] == ("step:download-genome-2",)
    assert active_log_contexts() == ()


def test_step_command_rejects_unknown_steps():
    runner = CliRunner()

    result = runner.invoke(main, ["step", "not-a-step"])

    assert result.exit_code != 0
    assert "Unknown step 'not-a-step'" in result.output


def test_step_command_preserves_nonzero_exit_code(monkeypatch):
    from ASOkai._pipeline.steps.core.download_genome import DownloadGenomeStep

    monkeypatch.setattr(DownloadGenomeStep, "run_cli", lambda self, argv: 3)

    result = CliRunner().invoke(main, ["step", "download-genome"])

    assert result.exit_code == 3


def test_publish_outputs_command_reports_publisher_errors(monkeypatch, tmp_path):
    manifest = tmp_path / "layout.yml"
    manifest.touch()
    source = tmp_path / "source.txt"
    source.touch()

    def reject_publication(*args, **kwargs):
        raise ValueError("invalid publication")

    monkeypatch.setattr(
        "ASOkai._cwl.publisher.publish_outputs",
        reject_publication,
    )

    result = CliRunner().invoke(
        main,
        ["publish-outputs", str(manifest), str(source)],
    )

    assert result.exit_code != 0
    assert "Error: invalid publication" in result.output
    assert "Traceback" not in result.output
