#!/usr/bin/env python
"""
Filename: tests/unit/test_step_cli.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Tests for the shared pipeline-step command-line lifecycle.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

from pathlib import Path
import sys

import pytest

from ASOkai.Plugins import (
    ExternalCommandStep,
    FileOutput,
    FileType,
    ScalarParam,
    Step,
    StepSpec,
)


class RequiredTextFile(FileType):
    """Test contract requiring one exact text value."""

    def validate(self, path) -> None:
        super().validate(path)
        if Path(path).read_text(encoding="utf-8") != "valid":
            raise ValueError("expected valid text")


class CliLifecycleStep(Step):
    name = "cli-lifecycle"
    description = "Exercise the shared CLI lifecycle."
    first_output = FileOutput(
        "first",
        destination="first.txt",
        file_type=RequiredTextFile(),
    )
    second_output = FileOutput(
        "second",
        destination="second.txt",
        file_type=RequiredTextFile(),
    )
    spec = StepSpec(
        params=[ScalarParam("count", int)],
        outputs=[first_output, second_output],
    )

    def run_from_args(self, args) -> int:
        assert args.first_output.parent.exists()
        assert args.second_output.parent.exists()
        args.first_output.write_text("valid", encoding="utf-8")
        args.second_output.write_text("valid", encoding="utf-8")
        return 0


class InvalidOutputStep(Step):
    name = "invalid-output"
    description = "Write an output that violates its contract."
    result_output = FileOutput(
        "result",
        destination="result.txt",
        file_type=RequiredTextFile(),
    )
    spec = StepSpec(outputs=[result_output])

    def run_from_args(self, args) -> int:
        args.result_output.write_text("invalid", encoding="utf-8")
        return 0


class MissingOutputStep(Step):
    name = "missing-output"
    description = "Return success without producing the declared output."
    result_output = FileOutput("result", destination="result.txt")
    spec = StepSpec(outputs=[result_output])

    def run_from_args(self, args) -> int:
        return 0


class ExternalWriterStep(ExternalCommandStep):
    name = "external-writer"
    description = "Write a validated output through an external command."
    result_output = FileOutput(
        "result",
        destination="result.txt",
        file_type=RequiredTextFile(),
    )
    spec = StepSpec(outputs=[result_output])

    def build_command(self, args):
        return [
            sys.executable,
            "-c",
            (
                "from pathlib import Path; import sys; "
                "Path(sys.argv[1]).write_text('valid', encoding='utf-8')"
            ),
            str(args.result_output),
        ]


class RelationshipValidatedStep(Step):
    name = "relationship-validated"
    description = "Exercise relationship validation before execution."
    result_output = FileOutput("result", destination="result.txt")
    spec = StepSpec(
        params=[ScalarParam("minimum", int), ScalarParam("maximum", int)],
        outputs=[result_output],
    )

    def validate_parameters(self, values):
        if values["minimum"] > values["maximum"]:
            raise ValueError("minimum must not exceed maximum")

    def run_from_args(self, args) -> int:
        raise AssertionError("invalid parameters must prevent execution")


class ParallelCliStep(Step):
    name = "parallel-cli"
    description = "Exercise the standard parallel-worker argument."
    supports_multiple_workers = True
    result_output = FileOutput("result", destination="result.txt")
    spec = StepSpec(outputs=[result_output])

    def run_from_args(self, args) -> int:
        raise AssertionError("an invalid worker count must prevent execution")


def test_run_cli_parses_and_prepares_every_output(tmp_path):
    first = tmp_path / "first" / "result.txt"
    second = tmp_path / "second" / "result.txt"

    result = CliLifecycleStep().run_cli(
        [
            "--count", "3",
            "--first-output", str(first),
            "--second-output", str(second),
        ]
    )

    assert result == 0
    assert first.parent.is_dir()
    assert second.parent.is_dir()
    assert first.read_text(encoding="utf-8") == "valid"
    assert second.read_text(encoding="utf-8") == "valid"


def test_run_cli_rejects_invalid_output_at_producer_completion(tmp_path):
    output = tmp_path / "result.txt"

    with pytest.raises(ValueError, match="wrote invalid output 'result'"):
        InvalidOutputStep().run_cli(["--result-output", str(output)])


def test_run_cli_rejects_missing_output_at_producer_completion(tmp_path):
    output = tmp_path / "result.txt"

    with pytest.raises(FileNotFoundError, match="did not write output 'result'"):
        MissingOutputStep().run_cli(["--result-output", str(output)])


def test_external_command_uses_the_same_output_validation_lifecycle(tmp_path):
    output = tmp_path / "result.txt"

    result = ExternalWriterStep().run_cli(["--result-output", str(output)])

    assert result == 0
    assert output.read_text(encoding="utf-8") == "valid"


def test_single_worker_step_has_no_worker_argument():
    assert "--n-workers" not in CliLifecycleStep().build_parser().format_help()


def test_run_cli_validates_parameter_relationships_before_creating_outputs(
    tmp_path,
    capsys,
):
    output = tmp_path / "nested" / "result.txt"

    with pytest.raises(SystemExit) as raised:
        RelationshipValidatedStep().run_cli(
            [
                "--minimum", "5",
                "--maximum", "3",
                "--result-output", str(output),
            ]
        )

    assert raised.value.code == 2
    assert "minimum must not exceed maximum" in capsys.readouterr().err
    assert not output.parent.exists()


def test_run_cli_rejects_non_positive_parallel_worker_count(tmp_path, capsys):
    output = tmp_path / "nested" / "result.txt"

    with pytest.raises(SystemExit) as raised:
        ParallelCliStep().run_cli(
            [
                "--n-workers", "0",
                "--result-output", str(output),
            ]
        )

    assert raised.value.code == 2
    assert "positive integer" in capsys.readouterr().err
    assert not output.parent.exists()


def test_step_output_must_be_declared_as_a_class_attribute():
    with pytest.raises(TypeError, match="must be declared once as a class attribute"):

        class InlineOutputStep(Step):
            name = "inline-output"
            description = "Invalid test step."
            spec = StepSpec(
                outputs=[FileOutput("result", destination="result.json")],
            )


def test_step_with_a_spec_requires_an_explicit_name():
    with pytest.raises(TypeError, match="requires a name"):

        class MissingNameStep(Step):
            description = "Invalid test step."
            spec = StepSpec()


def test_step_name_must_be_usable_as_a_run_identifier():
    with pytest.raises(TypeError, match="letters, numbers, hyphens"):

        class InvalidNameStep(Step):
            name = "invalid name"
            description = "Invalid test step."
            spec = StepSpec()


def test_step_output_paths_are_owned_by_file_output_destinations():
    with pytest.raises(TypeError, match="FileOutput.destination"):

        class CustomOutputPathsStep(Step):
            name = "custom-output-paths"
            description = "Invalid test step."
            spec = StepSpec()

            def output_paths(self, config):
                return {}


def test_step_cannot_override_output_validation_lifecycle():
    with pytest.raises(TypeError, match="framework-owned lifecycle method"):

        class CustomRunCliStep(Step):
            name = "custom-run-cli"
            description = "Invalid test step."
            spec = StepSpec()

            def run_cli(self, argv=None):
                return 0


def test_step_requires_values_for_every_declared_parameter():
    class ParameterizedStep(Step):
        name = "parameterized"
        description = "Test parameter resolution."
        spec = StepSpec(
            params=[
                ScalarParam("visible", str, config="values.visible"),
                ScalarParam(
                    "internal",
                    int,
                    config="values.internal",
                ),
                ScalarParam("missing", str, config="values.missing"),
                ScalarParam("unconfigured", str),
            ],
        )

    with pytest.raises(ValueError, match="values.missing"):
        ParameterizedStep().resolved_parameter_values(
            {"values": {"visible": "yes", "internal": 3}},
        )

    values = ParameterizedStep().resolved_parameter_values(
        {"values": {"visible": "yes", "internal": 3}},
        {"missing": "supplied", "unconfigured": "local"},
    )
    assert values == {
        "visible": "yes", "internal": 3,
        "missing": "supplied", "unconfigured": "local",
    }


class SchemaValidatedStep(Step):
    name = "schema-validated"
    description = "Apply a configuration field constraint through the shared CLI."
    result_output = FileOutput("result", destination="result.txt")
    spec = StepSpec(
        params=[ScalarParam("count", int, config="parameters.target.k", default=1)],
        outputs=[result_output],
    )

    def run_from_args(self, args) -> int:
        args.result_output.write_text(str(args.count), encoding="utf-8")
        return 0


@pytest.mark.parametrize("count", ["0", "-1"])
def test_run_cli_applies_config_schema_before_creating_outputs(tmp_path, capsys, count):
    output = tmp_path / "nested" / "result.txt"

    with pytest.raises(SystemExit) as raised:
        SchemaValidatedStep().run_cli(
            ["--count", count, "--result-output", str(output)]
        )

    assert raised.value.code == 2
    assert "parameters.target.k" in capsys.readouterr().err
    assert not output.parent.exists()


def test_run_cli_accepts_schema_valid_value_without_unrelated_config(tmp_path):
    output = tmp_path / "result.txt"
    assert SchemaValidatedStep().run_cli(
        ["--count", "4", "--result-output", str(output)]
    ) == 0
    assert output.read_text() == "4"
