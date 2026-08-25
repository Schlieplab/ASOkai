#!/usr/bin/env python
"""Tests for the shared pipeline-step command-line lifecycle."""

from __future__ import annotations

import pytest

from ASOkai.Plugins import FileOutput, ScalarParam, Step, StepSpec


class CliLifecycleStep(Step):
    name = "cli-lifecycle"
    description = "Exercise the shared CLI lifecycle."
    first_output = FileOutput("first", destination="first.txt")
    second_output = FileOutput("second", destination="second.txt")
    spec = StepSpec(
        params=[ScalarParam("count", int)],
        outputs=[first_output, second_output],
    )

    def run_from_args(self, args) -> int:
        assert args.first_output.parent.exists()
        assert args.second_output.parent.exists()
        return args.count


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

    assert result == 3
    assert first.parent.is_dir()
    assert second.parent.is_dir()


def test_single_process_step_has_no_process_argument():
    assert "--n-processes" not in CliLifecycleStep().build_parser().format_help()


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


def test_step_resolves_available_config_backed_parameters():
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
                    cwl=False,
                ),
                ScalarParam("missing", str, config="values.missing"),
                ScalarParam("unconfigured", str),
            ],
        )

    values = ParameterizedStep().resolved_parameter_values(
        {"values": {"visible": "yes", "internal": 3}},
    )

    assert values == {"visible": "yes", "internal": 3}
