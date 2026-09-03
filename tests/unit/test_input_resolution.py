#!/usr/bin/env python
"""
Filename: tests/unit/test_input_resolution.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Tests for concrete step-run input resolution.
License: LGPL-3.0-or-later
"""

from pathlib import Path

import pytest

from ASOkai.Plugins import FileInput, FileOutput, ScalarParam, Step, StepSpec
from ASOkai._cwl.input_resolution import (
    resolve_run_inputs,
    resolve_run_sequence_inputs,
    to_cwl_inputs,
)
from ASOkai._pipeline.contracts.execution import StepInputBinding, StepRun


class _BooleanStep(Step):
    name = "boolean-step"
    description = "Exercise native boolean CWL inputs."
    result_output = FileOutput("result", destination="boolean-step/result.txt")
    spec = StepSpec(
        params=[ScalarParam("enabled", bool, config="feature.enabled")],
        outputs=[result_output],
    )


def _fake_step(
    name: str,
    *,
    producer: Step | None = None,
    scalar_parameters: dict[str, str] | None = None,
    input_name: str | None = None,
    output_names: list[str] | None = None,
) -> Step:
    """Return an isolated fake step with class-level contract metadata."""
    outputs = [
        FileOutput(
            output_name,
            destination=f"{name}/{output_name}.txt",
        )
        for output_name in output_names or [f"{name}_out"]
    ]
    inputs = []
    if input_name is not None:
        if producer is None:
            raise ValueError("A test file input requires a producer.")
        inputs.append(
            FileInput(
                input_name,
                source=producer.spec.output(input_name),
            )
        )
    spec = StepSpec(
        params=[
            ScalarParam(parameter_name, str, config=config_path)
            for parameter_name, config_path in (scalar_parameters or {}).items()
        ],
        inputs=inputs,
        outputs=outputs,
    )
    step_type = type(
        f"_{name.replace('-', '_').title()}Step",
        (Step,),
        {
            "name": name,
            "description": "",
            "spec": spec,
            **{f"{output.name}_output": output for output in outputs},
        },
    )
    return step_type()


def _run(
    step: Step,
    config: dict,
    *,
    producer_run: StepRun | None = None,
    override: Path | None = None,
) -> StepRun:
    bindings = []
    if step.spec.inputs:
        file_input = step.spec.inputs[0]
        source = (
            override
            if override is not None
            else producer_run.output(file_input.source)
            if producer_run is not None
            else None
        )
        if source is None:
            raise ValueError("A test run with a file input requires a source.")
        bindings.append(StepInputBinding(file_input, source))
    return StepRun(
        run_id=step.name,
        step=step,
        config=config,
        inputs=tuple(bindings),
    )


@pytest.mark.parametrize("enabled", [False, True])
def test_boolean_flags_remain_native_cwl_values(tmp_path, enabled):
    run = StepRun(
        _BooleanStep.name,
        _BooleanStep(),
        {
            "datadir": str(tmp_path),
            "feature": {"enabled": enabled},
        },
    )

    assert resolve_run_inputs(run)["enabled"].cwl_value is enabled


def test_path_binding_is_resolved_as_input_override(tmp_path):
    config = {"datadir": str(tmp_path)}
    producer = _fake_step("producer", output_names=["shared"])
    consumer = _fake_step(
        "consumer",
        producer=producer,
        input_name="shared",
    )
    override = tmp_path / "override.fa"
    run = _run(consumer, config, override=override)

    resolved = resolve_run_inputs(run)

    assert resolved["shared"].source == "input_override"
    assert resolved["shared"].cwl_value == {
        "class": "File",
        "path": str(override.resolve()),
    }
    assert resolved["shared"].config_path == (
        "steps.consumer.inputs.shared.path_override"
    )


def test_scheduled_producer_output_is_wired(tmp_path):
    config = {"datadir": str(tmp_path)}
    producer = _fake_step("producer", output_names=["result"])
    consumer = _fake_step(
        "consumer",
        producer=producer,
        input_name="result",
    )
    producer_run = _run(producer, config)
    consumer_run = _run(consumer, config, producer_run=producer_run)

    resolved = resolve_run_inputs(
        consumer_run,
        runs_to_execute={producer_run, consumer_run},
    )

    assert resolved["result"].source == "dep_wired"
    assert resolved["result"].cwl_value is None
    assert resolved["result"].producer_output == producer_run.output(
        producer.spec.output("result")
    )
    assert "result" not in to_cwl_inputs(resolved)


def test_distinct_run_with_same_id_does_not_wire_producer_output(tmp_path):
    config = {"datadir": str(tmp_path)}
    producer = _fake_step("producer", output_names=["result"])
    consumer = _fake_step(
        "consumer",
        producer=producer,
        input_name="result",
    )
    producer_run = _run(producer, config)
    different_producer_run = _run(producer, config)
    consumer_run = _run(consumer, config, producer_run=producer_run)
    producer_output = producer_run.output(producer.spec.output("result"))
    path = tmp_path / "producer-result.txt"

    resolved = resolve_run_inputs(
        consumer_run,
        resolved_outputs={producer_output: path},
        runs_to_execute={different_producer_run, consumer_run},
    )

    assert resolved["result"].source == "dep_disk"
    assert resolved["result"].path == path


def test_reused_producer_output_is_read_from_disk(tmp_path):
    config = {"datadir": str(tmp_path)}
    producer = _fake_step("producer", output_names=["result"])
    consumer = _fake_step(
        "consumer",
        producer=producer,
        input_name="result",
    )
    producer_run = _run(producer, config)
    consumer_run = _run(consumer, config, producer_run=producer_run)
    producer_output = producer_run.output(producer.spec.output("result"))
    path = tmp_path / "producer-result.txt"

    resolved = resolve_run_inputs(
        consumer_run,
        resolved_outputs={producer_output: path},
    )

    assert resolved["result"].source == "dep_disk"
    assert resolved["result"].cwl_value == {
        "class": "File",
        "path": str(path.resolve()),
    }


def test_missing_reused_output_is_rejected(tmp_path):
    config = {"datadir": str(tmp_path)}
    producer = _fake_step("producer", output_names=["result"])
    consumer = _fake_step(
        "consumer",
        producer=producer,
        input_name="result",
    )
    producer_run = _run(producer, config)
    consumer_run = _run(consumer, config, producer_run=producer_run)

    with pytest.raises(RuntimeError, match="requires resolved output"):
        resolve_run_inputs(consumer_run)


def test_sequence_qualifies_matching_values_by_run(tmp_path):
    config = {
        "datadir": str(tmp_path),
        "shared": {"mode": "fast"},
    }
    first = _fake_step(
        "first",
        scalar_parameters={"mode": "shared.mode"},
    )
    second = _fake_step(
        "second",
        scalar_parameters={"mode": "shared.mode"},
    )

    resolved = resolve_run_sequence_inputs(
        [_run(first, config), _run(second, config)],
        {},
    )

    assert resolved == {
        "first.mode": "fast",
        "second.mode": "fast",
    }


def test_sequence_reuses_one_input_for_one_producer_output(tmp_path):
    config = {"datadir": str(tmp_path)}
    producer = _fake_step("producer", output_names=["result"])
    first = _fake_step(
        "first",
        producer=producer,
        input_name="result",
    )
    second = _fake_step(
        "second",
        producer=producer,
        input_name="result",
    )
    producer_run = _run(producer, config)
    producer_output = producer_run.output(producer.spec.output("result"))
    path = tmp_path / "producer-result.txt"

    resolved = resolve_run_sequence_inputs(
        [
            _run(first, config, producer_run=producer_run),
            _run(second, config, producer_run=producer_run),
        ],
        {producer_output: path},
    )

    assert resolved == {
        "producer.result": {
            "class": "File",
            "path": str(path.resolve()),
        },
    }


def test_sequence_keeps_path_overrides_qualified_by_consumer(tmp_path):
    config = {"datadir": str(tmp_path)}
    producer = _fake_step("producer", output_names=["result"])
    first = _fake_step(
        "first",
        producer=producer,
        input_name="result",
    )
    second = _fake_step(
        "second",
        producer=producer,
        input_name="result",
    )
    path = tmp_path / "override.txt"

    resolved = resolve_run_sequence_inputs(
        [
            _run(first, config, override=path),
            _run(second, config, override=path),
        ],
        {},
    )

    file_value = {
        "class": "File",
        "path": str(path.resolve()),
    }
    assert resolved == {
        "first.result": file_value,
        "second.result": file_value,
    }
