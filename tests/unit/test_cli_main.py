#!/usr/bin/env python
"""
Filename: tests/unit/test_cli_main.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Tests for the public ASOkai CLI entrypoint.
License: LGPL-3.0-or-later
"""

import logging
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
    workflows = runner.invoke(main, ["list", "workflows"])

    assert steps.exit_code == 0
    assert "Core\n" in steps.output
    assert "Analysis\n" in steps.output
    assert "download-genome" in steps.output
    assert "Downloads genome DNA" in steps.output
    assert "create-target-gene" in steps.output
    assert "generate-aso-candidates" in steps.output
    assert "intrinsic-features" in steps.output
    assert "target-gene-to-fasta" not in steps.output
    assert "[Per site] Computes nucleotide composition" in steps.output

    assert tasks.exit_code == 0
    assert "instantiate-target-gene" in tasks.output
    assert "index-target-gene" in tasks.output
    assert "Downloads genome data" in tasks.output

    assert workflows.exit_code == 0
    assert "standard" in workflows.output
    assert "Standard pipeline" in workflows.output

    verbose_steps = runner.invoke(main, ["list", "-v", "steps"])
    assert verbose_steps.exit_code == 0
    assert "target-gene-to-fasta" in verbose_steps.output


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
    hidden = runner.invoke(main, ["describe", "step", "download-genome"])
    described = runner.invoke(main, ["describe", "-v", "step", "download-genome"])

    assert public.exit_code == verbose.exit_code == described.exit_code == 0
    assert "download-genome" not in public.output
    assert "download-genome" in verbose.output
    assert "Internal\n" in verbose.output
    assert hidden.exit_code != 0
    assert "Unknown step 'download-genome'" in hidden.output
    assert "Type        : Internal" in described.output


def test_describe_step_create_target_gene_shows_details():
    runner = CliRunner()

    result = runner.invoke(main, ["describe", "step", "create-target-gene"])

    assert result.exit_code == 0
    assert "Name        : create-target-gene" in result.output
    assert "Type        : Core" in result.output
    assert "Run parameters:" in result.output
    assert "--param target_id=VALUE" in result.output
    assert "--param region=VALUE" in result.output
    assert "config key: parameters.target.target_id" in result.output
    assert "config key: parameters.target.region" in result.output
    assert "Input configuration (optional):" in result.output
    assert "steps.create-target-gene.inputs.dna.path_override" in result.output
    assert "--config " not in result.output
    assert "Dependencies: download-genome" in result.output


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
    assert "CWL         : (CLI collection; export creates run.cwl)" in result.output
    assert "Steps: download-genome, create-target-gene" in result.output


def test_describe_workflow_shows_members_and_expanded_steps():
    runner = CliRunner()

    result = runner.invoke(main, ["describe", "workflow", "standard"])

    assert result.exit_code == 0
    assert "Name        : standard" in result.output
    assert (
        "Members     : instantiate-target-gene, generate-aso-candidates, "
        "intrinsic-features" in result.output
    )
    assert "CWL         : (CLI collection; export creates run.cwl)" in result.output
    assert (
        "Steps (expanded): download-genome, create-target-gene, "
        "generate-aso-candidates, intrinsic-features" in result.output
    )


def test_verbose_describe_step_shows_dependency_tree():
    runner = CliRunner()

    result = runner.invoke(
        main, ["describe", "--verbose", "step", "intrinsic-features"]
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
            "release=115",
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
        {"task": "instantiate-target-gene"},
        {"step": "generate-aso-candidates"},
        {"step": "intrinsic-features"},
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
        {"step": "download-genome"},
        {"step": "create-target-gene"},
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
    assert captured["config"]["runs"] == [{"task": "instantiate-target-gene"}]


@pytest.mark.parametrize("command", ["run", "export"])
def test_cli_run_options_match_ordered_yaml_declarations(
    monkeypatch, tmp_path, command
):
    captured = {}
    catalog = SimpleNamespace(
        steps={"create-target-gene": object(), "generate-aso-candidates": object()},
        tasks={"compare-regions": object()},
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
            "--step",
            "create-target-gene",
            "--id",
            "reference-gene",
            "--param",
            "region=pre-mrna",
            "--step",
            "generate-aso-candidates",
            "--id",
            "candidates",
            "--from-run",
            "target_gene=reference-gene.target_gene",
            "--task",
            "compare-regions",
            "--id",
            "comparison",
            "--param",
            "k=21",
            "--child",
            "transcriptomic",
            "--param",
            "k=18",
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
            "step": "generate-aso-candidates",
            "id": "candidates",
            "inputs": {"target_gene": {"from": "run.reference-gene.target_gene"}},
        },
        {
            "task": "compare-regions",
            "id": "comparison",
            "parameters": {"k": 21},
            "runs": [{"id": "transcriptomic", "parameters": {"k": 18}}],
        },
    ]


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (["--param", "k=21"], "must follow --step or --task"),
        (
            ["--task", "instantiate-target-gene", "--from-run", "dna=gene.dna"],
            "requires --child",
        ),
        (["--step", "download-genome", "--child", "gene"], "must follow a task"),
        (
            ["--step", "download-genome", "--param", "k=21", "--param", "k=18"],
            "Duplicate --param",
        ),
    ],
)
def test_cli_rejects_misplaced_run_options(args, message):
    result = CliRunner().invoke(main, ["run", *args])

    assert result.exit_code != 0
    assert message in result.output


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
            "k=21",
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
        {"task": "instantiate-target-gene", "parameters": {"k": 21}},
        {
            "step": "create-target-gene",
            "id": "custom",
            "inputs": {"dna": {"path": str(tmp_path / "genome.fa")}},
        },
        {"step": "download-genome"},
    ]


def test_cli_rejects_selection_alongside_configured_runs(monkeypatch):
    monkeypatch.setattr(
        "ASOkai._cli.execution.cfg.load",
        lambda _path: {"runs": [{"step": "download-genome"}]},
    )

    result = CliRunner().invoke(main, ["run", "--step", "create-target-gene"])

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
        {"step": "download-genome"},
        {"step": "create-target-gene"},
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
        {"task": "instantiate-target-gene"},
        {"step": "generate-aso-candidates"},
        {"step": "intrinsic-features"},
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
    assert captured["config"]["runs"] == [{"task": "instantiate-target-gene"}]


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
    assert captured["config"]["runs"] == [{"step": "download-genome"}]


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
            "create-target-gene",
            "--param",
            "k=20",
            "--param",
            "flag=true",
            "--param",
            "name=null",
        ],
    )

    assert result.exit_code == 0
    assert captured["config"]["runs"] == [
        {
            "step": "create-target-gene",
            "parameters": {"k": 20, "flag": True, "name": None},
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
