#!/usr/bin/env python
"""
Filename: tests/unit/test_output_receipts.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Tests for persistent generated-output validation receipts.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

import json
from pathlib import Path

from ASOkai.Plugins import (
    FileInput,
    FileOutput,
    ScalarParam,
    Step,
    StepSpec,
)
from ASOkai._pipeline.contracts.execution import StepInputBinding, StepRun
from ASOkai._pipeline.output_receipts import (
    receipt_path,
    record_validated_outputs,
    reusable_output_paths,
)


class MultiOutputStep(Step):
    name = "multi-output"
    description = "Produce two related test outputs."
    first_output = FileOutput("first", destination="results/first.txt")
    second_output = FileOutput("second", destination="results/second.txt")
    spec = StepSpec(outputs=[first_output, second_output])


class ParameterStep(Step):
    name = "parameter-step"
    description = "Produce a fixed-path result from a configured parameter."
    result_output = FileOutput("result", destination="parameter/result.txt")
    spec = StepSpec(
        params=[ScalarParam("mode", str, config="mode")],
        outputs=[result_output],
    )


class VersionOneStep(Step):
    name = "versioned-step"
    description = "Produce the first version of a result."
    result_output = FileOutput("result", destination="versioned/result.txt")
    spec = StepSpec(outputs=[result_output])


class VersionTwoStep(Step):
    name = "versioned-step"
    description = "Produce the second version of a result."
    cache_version = 2
    result_output = FileOutput("result", destination="versioned/result.txt")
    spec = StepSpec(outputs=[result_output])


class OverrideProducerStep(Step):
    name = "override-producer"
    description = "Declare the contract inherited by an overridden input."
    result_output = FileOutput("result", destination="producer/result.txt")
    spec = StepSpec(outputs=[result_output])


class OverrideConsumerStep(Step):
    name = "override-consumer"
    description = "Produce a result from an external path override."
    result_input = FileInput(
        "result",
        source=OverrideProducerStep.result_output,
    )
    summary_output = FileOutput("summary", destination="consumer/summary.txt")
    spec = StepSpec(inputs=[result_input], outputs=[summary_output])


def _materialize_and_record(run: StepRun) -> dict[str, Path]:
    paths = run.output_paths()
    for name, path in paths.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(name, encoding="utf-8")
    run.validate_output_files()
    record_validated_outputs(run)
    return paths


def test_unchanged_complete_output_set_is_reusable(tmp_path):
    run = StepRun("multi-output", MultiOutputStep(), {"datadir": str(tmp_path)})
    paths = _materialize_and_record(run)

    assert reusable_output_paths(run) == paths

    receipt = json.loads(receipt_path(run).read_text(encoding="utf-8"))
    assert set(receipt) == {"version", "run_signature", "outputs"}
    assert [output["name"] for output in receipt["outputs"]] == [
        "first",
        "second",
    ]


def test_changed_member_invalidates_complete_output_set(tmp_path):
    run = StepRun("multi-output", MultiOutputStep(), {"datadir": str(tmp_path)})
    paths = _materialize_and_record(run)

    paths["second"].write_text("changed contents", encoding="utf-8")

    assert reusable_output_paths(run) is None


def test_missing_member_invalidates_complete_output_set(tmp_path):
    run = StepRun("multi-output", MultiOutputStep(), {"datadir": str(tmp_path)})
    paths = _materialize_and_record(run)

    paths["first"].unlink()

    assert reusable_output_paths(run) is None


def test_parameter_change_invalidates_same_destination(tmp_path):
    first = StepRun(
        "parameter-step",
        ParameterStep(),
        {"datadir": str(tmp_path), "mode": "first"},
    )
    _materialize_and_record(first)
    second = StepRun(
        "parameter-step",
        ParameterStep(),
        {"datadir": str(tmp_path), "mode": "second"},
    )

    assert receipt_path(second) == receipt_path(first)
    assert reusable_output_paths(second) is None


def test_cache_version_change_invalidates_same_destination(tmp_path):
    first = StepRun(
        "versioned-step",
        VersionOneStep(),
        {"datadir": str(tmp_path)},
    )
    _materialize_and_record(first)
    second = StepRun(
        "versioned-step",
        VersionTwoStep(),
        {"datadir": str(tmp_path)},
    )

    assert receipt_path(second) == receipt_path(first)
    assert reusable_output_paths(second) is None


def test_malformed_receipt_is_not_reused(tmp_path):
    run = StepRun("multi-output", MultiOutputStep(), {"datadir": str(tmp_path)})
    _materialize_and_record(run)
    receipt_path(run).write_text("{not-json", encoding="utf-8")

    assert reusable_output_paths(run) is None


def test_override_affects_run_identity_without_receiving_a_receipt(tmp_path):
    override = tmp_path / "override.txt"
    override.write_text("first", encoding="utf-8")
    run = StepRun(
        "override-consumer",
        OverrideConsumerStep(),
        {"datadir": str(tmp_path)},
        inputs=(
            StepInputBinding(
                OverrideConsumerStep.result_input,
                override,
            ),
        ),
    )
    _materialize_and_record(run)

    override.write_text("changed contents", encoding="utf-8")

    assert reusable_output_paths(run) is None
    assert sorted(path.name for path in tmp_path.glob("override*")) == [
        "override.txt"
    ]
