#!/usr/bin/env python
"""Tests for the shared pipeline-step command-line lifecycle."""

from __future__ import annotations

from ASOkai.plugin_api import FileOutput, ScalarParam, Step, StepSpec


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
