"""Tests for the public ASOkai CLI entrypoint."""

from click.testing import CliRunner

from ASOkai._cli.main import main


def test_hidden_step_command_is_not_listed_in_help():
    runner = CliRunner()

    result = runner.invoke(main, ["--help"])

    assert result.exit_code == 0
    assert " step " not in result.output


def test_run_help_uses_configfile_and_config_override_options():
    runner = CliRunner()

    result = runner.invoke(main, ["run", "--help"])

    assert result.exit_code == 0
    assert "--configfile, --config-file PATH" in result.output
    assert "--executor [toil|cwltool]" in result.output
    assert "--config KEY=VALUE [KEY=VALUE ...]" in result.output
    assert "--set" not in result.output


def test_list_commands_show_registered_units():
    runner = CliRunner()

    steps = runner.invoke(main, ["list", "steps"])
    tasks = runner.invoke(main, ["list", "tasks"])
    workflows = runner.invoke(main, ["list", "workflows"])

    assert steps.exit_code == 0
    assert "download-genome" in steps.output
    assert "[core] Downloads genome DNA" in steps.output
    assert "create-target-gene" in steps.output
    assert "intrinsic-features" in steps.output

    assert tasks.exit_code == 0
    assert "instantiate-target-gene" in tasks.output
    assert "[core] Downloads genome data" in tasks.output

    assert workflows.exit_code == 0
    assert "standard" in workflows.output
    assert "Full pipeline" in workflows.output


def test_describe_step_create_target_gene_shows_details():
    runner = CliRunner()

    result = runner.invoke(main, ["describe", "step", "create-target-gene"])

    assert result.exit_code == 0
    assert "Name        : create-target-gene" in result.output
    assert "CWL         :" in result.output
    assert "create-target-gene.cwl" in result.output
    assert "Config keys :" in result.output
    assert "--config target.target_id" in result.output
    assert "--config target.region" in result.output
    assert "Input overrides (optional, bypasses dep step):" in result.output
    assert "--config genome.dna_path" in result.output
    assert "Dependencies: download-genome" in result.output


def test_describe_task_expands_step_names():
    runner = CliRunner()

    result = runner.invoke(main, ["describe", "task", "instantiate-target-gene"])

    assert result.exit_code == 0
    assert "Name        : instantiate-target-gene" in result.output
    assert "Steps       : download-genome, create-target-gene" in result.output
    assert "Steps: download-genome, create-target-gene" in result.output


def test_describe_workflow_shows_members_and_expanded_steps():
    runner = CliRunner()

    result = runner.invoke(main, ["describe", "workflow", "standard"])

    assert result.exit_code == 0
    assert "Name        : standard" in result.output
    assert "Members     : instantiate-target-gene, intrinsic-features" in result.output
    assert (
        "Steps (expanded): download-genome, create-target-gene, intrinsic-features"
        in result.output
    )


def test_verbose_describe_step_shows_dependency_tree():
    runner = CliRunner()

    result = runner.invoke(main, ["describe", "--verbose", "step", "intrinsic-features"])

    assert result.exit_code == 0
    assert "Dependencies:" in result.output
    assert "`-- create-target-gene" in result.output
    assert "`-- download-genome" in result.output


def test_run_config_accepts_multiple_values_after_one_flag(monkeypatch):
    captured = {}

    monkeypatch.setattr("ASOkai._cli.main.cfg.load", lambda _path: {"target": {"k": 16}})
    monkeypatch.setattr(
        "ASOkai._cli.main.runner.run_all",
        lambda runnables, config, **kwargs: captured.update(config=config),
    )

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "run",
            "--steps",
            "download-genome",
            "--config",
            "target.k=20",
            "target.region=exonic_only",
        ],
    )

    assert result.exit_code == 0
    assert captured["config"]["target"]["k"] == 20
    assert captured["config"]["target"]["region"] == "exonic_only"


def test_run_config_accepts_repeated_flags(monkeypatch):
    captured = {}

    monkeypatch.setattr("ASOkai._cli.main.cfg.load", lambda _path: {"target": {"k": 16}})
    monkeypatch.setattr(
        "ASOkai._cli.main.runner.run_all",
        lambda runnables, config, **kwargs: captured.update(config=config),
    )

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "run",
            "--steps",
            "download-genome",
            "--config",
            "target.k=20",
            "--config",
            "target.region=exonic_only",
        ],
    )

    assert result.exit_code == 0
    assert captured["config"]["target"]["k"] == 20
    assert captured["config"]["target"]["region"] == "exonic_only"


def test_run_requires_explicit_runnable_selection(monkeypatch):
    monkeypatch.setattr("ASOkai._cli.main.cfg.load", lambda _path: {})

    runner = CliRunner()
    result = runner.invoke(main, ["run"])

    assert result.exit_code != 0
    assert "Select at least one runnable" in result.output


def test_run_workflow_selects_standard_explicitly(monkeypatch):
    captured = {}

    monkeypatch.setattr("ASOkai._cli.main.cfg.load", lambda _path: {})
    monkeypatch.setattr(
        "ASOkai._cli.main.runner.run_all",
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


def test_run_steps_accepts_multiple_values_after_one_flag(monkeypatch):
    captured = {}

    monkeypatch.setattr("ASOkai._cli.main.cfg.load", lambda _path: {})
    monkeypatch.setattr(
        "ASOkai._cli.main.runner.run_all",
        lambda runnables, config, **kwargs: captured.update(runnables=runnables),
    )

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["run", "--steps", "download-genome", "create-target-gene"],
    )

    assert result.exit_code == 0
    assert [r.name for r in captured["runnables"]] == [
        "download-genome",
        "create-target-gene",
    ]


def test_run_tasks_accepts_multiple_values_after_one_flag(monkeypatch):
    captured = {}

    monkeypatch.setattr("ASOkai._cli.main.cfg.load", lambda _path: {})
    monkeypatch.setattr(
        "ASOkai._cli.main.runner.run_all",
        lambda runnables, config, **kwargs: captured.update(runnables=runnables),
    )

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["run", "--tasks", "instantiate-target-gene"],
    )

    assert result.exit_code == 0
    assert [r.name for r in captured["runnables"]] == ["instantiate-target-gene"]


def test_run_uses_toil_executor_when_requested(monkeypatch):
    captured = {}

    monkeypatch.setattr("ASOkai._cli.main.cfg.load", lambda _path: {})
    monkeypatch.setattr(
        "ASOkai._cli.main.runner.run_all",
        lambda runnables, config, **kwargs: captured.update(kwargs),
    )

    runner = CliRunner()
    result = runner.invoke(main, ["run", "--steps", "download-genome", "--executor", "toil"])

    assert result.exit_code == 0
    assert captured["executor"].__class__.__name__ == "ToilExecutor"


def test_run_export_only_without_value_uses_datadir_jobs(monkeypatch, tmp_path):
    captured = {}

    monkeypatch.setattr(
        "ASOkai._cli.main.cfg.load",
        lambda _path: {"datadir": str(tmp_path / "data")},
    )
    monkeypatch.setattr(
        "ASOkai._cli.main.runner.run_all",
        lambda runnables, config, **kwargs: captured.update(kwargs),
    )

    runner = CliRunner()
    result = runner.invoke(main, ["run", "--workflow", "standard", "--export-only"])

    assert result.exit_code == 0
    assert captured["export_only"] == tmp_path / "data" / "jobs"


def test_run_export_only_with_value_uses_explicit_parent(monkeypatch, tmp_path):
    captured = {}

    monkeypatch.setattr(
        "ASOkai._cli.main.cfg.load",
        lambda _path: {"datadir": str(tmp_path / "data")},
    )
    monkeypatch.setattr(
        "ASOkai._cli.main.runner.run_all",
        lambda runnables, config, **kwargs: captured.update(kwargs),
    )

    export_parent = tmp_path / "jobs"
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["run", "--workflow", "standard", "--export-only", str(export_parent)],
    )

    assert result.exit_code == 0
    assert captured["export_only"] == export_parent


def test_run_export_only_rejects_export_cwl(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "ASOkai._cli.main.cfg.load",
        lambda _path: {"datadir": str(tmp_path / "data")},
    )

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "run",
            "--workflow",
            "standard",
            "--export-only",
            "--export-cwl",
            str(tmp_path / "workflow.cwl"),
        ],
    )

    assert result.exit_code != 0
    assert "mutually exclusive" in result.output


def test_run_rejects_unknown_step(monkeypatch):
    monkeypatch.setattr("ASOkai._cli.main.cfg.load", lambda _path: {})

    runner = CliRunner()
    result = runner.invoke(main, ["run", "--steps", "not-a-step"])

    assert result.exit_code != 0
    assert "Unknown step 'not-a-step'." in result.output


def test_run_rejects_unknown_task(monkeypatch):
    monkeypatch.setattr("ASOkai._cli.main.cfg.load", lambda _path: {})

    runner = CliRunner()
    result = runner.invoke(main, ["run", "--tasks", "not-a-task"])

    assert result.exit_code != 0
    assert "Unknown task 'not-a-task'." in result.output


def test_run_rejects_unknown_workflow(monkeypatch):
    monkeypatch.setattr("ASOkai._cli.main.cfg.load", lambda _path: {})

    runner = CliRunner()
    result = runner.invoke(main, ["run", "--workflow", "not-a-workflow"])

    assert result.exit_code != 0
    assert "Unknown workflow 'not-a-workflow'." in result.output


def test_run_config_rejects_malformed_override(monkeypatch):
    monkeypatch.setattr("ASOkai._cli.main.cfg.load", lambda _path: {})

    runner = CliRunner()
    result = runner.invoke(main, ["run", "--config", "target.k"])

    assert result.exit_code != 0
    assert "KEY=VALUE format" in result.output


def test_run_config_preserves_yaml_scalar_types(monkeypatch):
    captured = {}

    monkeypatch.setattr("ASOkai._cli.main.cfg.load", lambda _path: {"target": {}})
    monkeypatch.setattr(
        "ASOkai._cli.main.runner.run_all",
        lambda runnables, config, **kwargs: captured.update(config=config),
    )

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "run",
            "--steps",
            "download-genome",
            "--config",
            "target.k=20",
            "target.flag=true",
            "target.name=null",
        ],
    )

    assert result.exit_code == 0
    assert captured["config"]["target"]["k"] == 20
    assert captured["config"]["target"]["flag"] is True
    assert captured["config"]["target"]["name"] is None


def test_step_command_dispatches_to_builtin_step(monkeypatch):
    from ASOkai._pipeline.steps import download_genome

    received: dict[str, list[str] | None] = {}

    def fake_main(argv: list[str] | None = None) -> int:
        received["argv"] = argv
        return 0

    monkeypatch.setattr(download_genome, "main", fake_main)

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["step", "download-genome", "--assembly", "GRCh38", "--release", "114"],
    )

    assert result.exit_code == 0
    assert received["argv"] == ["--assembly", "GRCh38", "--release", "114"]


def test_step_command_rejects_unknown_steps():
    runner = CliRunner()

    result = runner.invoke(main, ["step", "not-a-step"])

    assert result.exit_code != 0
    assert "Unknown step 'not-a-step'" in result.output
