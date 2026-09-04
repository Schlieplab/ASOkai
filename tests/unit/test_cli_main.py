#!/usr/bin/env python
"""
Filename: tests/unit/test_cli_main.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Tests for the public ASOkai CLI entrypoint.
License: LGPL-3.0-or-later
"""

import logging

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
        "[workflow:standard] First line\n\n"
        "[workflow:standard] Second line"
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


def test_run_help_uses_configfile_and_config_override_options():
    runner = CliRunner()

    result = runner.invoke(main, ["run", "--help"])
    short_result = runner.invoke(main, ["run", "-h"])

    assert result.exit_code == 0
    assert short_result.exit_code == 0
    assert "--configfile, --config-file FILE" in short_result.output
    assert "--configfile, --config-file FILE" in result.output
    assert "--executor [toil|cwltool]" in result.output
    assert "--config KEY=VALUE" in result.output
    assert "--non-recursive" in result.output
    assert "--recursive" not in result.output
    assert "--set" not in result.output


def test_export_help_uses_explicit_recursive_option():
    runner = CliRunner()

    result = runner.invoke(main, ["export", "--help"])

    assert result.exit_code == 0
    assert "--recursive" in result.output
    assert "--non-recursive" not in result.output


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
    assert "[Site-specific] Computes nucleotide composition" in steps.output

    assert tasks.exit_code == 0
    assert "instantiate-target-gene" in tasks.output
    assert "Downloads genome data" in tasks.output

    assert workflows.exit_code == 0
    assert "standard" in workflows.output
    assert "Standard pipeline" in workflows.output


def test_describe_step_create_target_gene_shows_details():
    runner = CliRunner()

    result = runner.invoke(main, ["describe", "step", "create-target-gene"])

    assert result.exit_code == 0
    assert "Name        : create-target-gene" in result.output
    assert "Type        : Core" in result.output
    assert "Config keys :" in result.output
    assert "--config target.target_id" in result.output
    assert "--config target.region" in result.output
    assert "Input configuration (optional):" in result.output
    assert "--config steps.create-target-gene.inputs.dna.path_override" in result.output
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
    assert (
        "Description : [Site-specific] Computes nucleotide composition" in result.output
    )
    assert "Dependencies:" in result.output
    assert "`-- create-target-gene" in result.output
    assert "`-- download-genome" in result.output


def test_run_config_accepts_repeated_flags(monkeypatch):
    captured = {}

    monkeypatch.setattr(
        "ASOkai._cli.execution.cfg.load", lambda _path, **_kwargs: {"target": {"k": 16}}
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
            "download-genome",
            "--config",
            "target.k=20",
            "--config",
            "target.region=exonic",
        ],
    )

    assert result.exit_code == 0
    assert captured["config"]["target"]["k"] == 20
    assert captured["config"]["target"]["region"] == "exonic"


def test_run_requires_explicit_runnable_selection():
    runner = CliRunner()
    result = runner.invoke(main, ["run"])

    assert result.exit_code != 0
    assert "Select at least one runnable" in result.output


def test_run_workflow_selects_standard_explicitly(monkeypatch):
    captured = {}

    monkeypatch.setattr("ASOkai._cli.execution.cfg.load", lambda _path, **_kwargs: {})
    monkeypatch.setattr(
        "ASOkai._cli.execution.runner.run_all",
        lambda runnables, config, **kwargs: captured.update(
            runnables=runnables,
            **kwargs,
        ),
    )

    runner = CliRunner()
    result = runner.invoke(main, ["run", "--workflow", "standard"])

    assert result.exit_code == 0
    assert [r.name for r in captured["runnables"]] == ["standard"]
    assert captured["executor"].__class__.__name__ == "CwlToolExecutor"


def test_run_steps_accepts_repeated_flags(monkeypatch):
    captured = {}

    monkeypatch.setattr("ASOkai._cli.execution.cfg.load", lambda _path, **_kwargs: {})
    monkeypatch.setattr(
        "ASOkai._cli.execution.runner.run_all",
        lambda runnables, config, **kwargs: captured.update(runnables=runnables),
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
    assert [r.name for r in captured["runnables"]] == [
        "download-genome",
        "create-target-gene",
    ]


def test_run_resolves_task_selection(monkeypatch):
    captured = {}

    monkeypatch.setattr("ASOkai._cli.execution.cfg.load", lambda _path, **_kwargs: {})
    monkeypatch.setattr(
        "ASOkai._cli.execution.runner.run_all",
        lambda runnables, config, **kwargs: captured.update(runnables=runnables),
    )

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["run", "--task", "instantiate-target-gene"],
    )

    assert result.exit_code == 0
    assert [r.name for r in captured["runnables"]] == ["instantiate-target-gene"]


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
    assert [r.name for r in captured["runnables"]] == [
        "download-genome",
        "create-target-gene",
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
            **kwargs,
        )
        or tmp_path / "data" / "jobs" / "asokai-export-1",
    )

    runner = CliRunner()
    result = runner.invoke(main, ["export", "--workflow", "standard"])

    assert result.exit_code == 0
    assert [r.name for r in captured["runnables"]] == ["standard"]
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
            **kwargs,
        )
        or tmp_path / "data" / "jobs" / "asokai-export-1",
    )

    runner = CliRunner()
    result = runner.invoke(main, ["export", "--task", "instantiate-target-gene"])

    assert result.exit_code == 0
    assert [r.name for r in captured["runnables"]] == ["instantiate-target-gene"]


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


def test_run_config_rejects_malformed_override(monkeypatch):
    monkeypatch.setattr("ASOkai._cli.execution.cfg.load", lambda _path, **_kwargs: {})

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "run",
            "--step",
            "download-genome",
            "--config",
            "target.k",
        ],
    )

    assert result.exit_code != 0
    assert "KEY=VALUE format" in result.output


def test_run_config_reports_invalid_yaml_value(monkeypatch):
    monkeypatch.setattr("ASOkai._cli.execution.cfg.load", lambda _path: {})

    result = CliRunner().invoke(
        main,
        [
            "run",
            "--step",
            "download-genome",
            "--config",
            "target.k=[",
        ],
    )

    assert result.exit_code != 0
    assert "Invalid value for --config" in result.output
    assert "invalid YAML value" in result.output


def test_run_applies_overrides_before_runner_validation(monkeypatch, tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "datadir: .\n" "genome:\n" "  source: ''\n",
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
            "--config",
            "genome.source=ensembl",
        ],
    )

    assert result.exit_code == 0
    assert captured["config"]["genome"]["source"] == "ensembl"


def test_run_displays_configuration_errors_without_traceback(monkeypatch):
    monkeypatch.setattr(
        "ASOkai._cli.execution.cfg.load",
        lambda _path, **_kwargs: {"datadir": "./data"},
    )

    def reject_config(*args, **kwargs):
        raise ValueError("Invalid configuration:\n- $.target.k: 0 is less than 1")

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
    assert "$.target.k" in result.output
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
        raise ValueError("Invalid configuration:\n- $.target.region: invalid")

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
    assert "$.target.region" in result.output
    assert "Traceback" not in result.output


def test_run_config_preserves_yaml_scalar_types(monkeypatch):
    captured = {}

    monkeypatch.setattr(
        "ASOkai._cli.execution.cfg.load", lambda _path, **_kwargs: {"target": {}}
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
            "download-genome",
            "--config",
            "target.k=20",
            "--config",
            "target.flag=true",
            "--config",
            "target.name=null",
        ],
    )

    assert result.exit_code == 0
    assert captured["config"]["target"]["k"] == 20
    assert captured["config"]["target"]["flag"] is True
    assert captured["config"]["target"]["name"] is None


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
