#!/usr/bin/env python
"""Tests for concrete step-run and execution-plan contracts."""

from pathlib import Path

import pytest

from ASOkai.Plugins import FileInput, FileOutput, Step, StepSpec
from ASOkai._pipeline.contracts.execution import (
    ExecutionPlan,
    StepInputBinding,
    StepRun,
    StepRunOutput,
)


class ProducerStep(Step):
    name = "producer"
    description = "Produce a test file."
    result_output = FileOutput("result", destination="result.txt")
    spec = StepSpec(outputs=[result_output])


class OtherProducerStep(Step):
    name = "other-producer"
    description = "Produce a different test file."
    result_output = FileOutput("result", destination="other-result.txt")
    spec = StepSpec(outputs=[result_output])


class ConsumerStep(Step):
    name = "consumer"
    description = "Consume the test file."
    result_input = FileInput("result", source=ProducerStep.result_output)
    spec = StepSpec(inputs=[result_input])


@pytest.mark.parametrize(
    "run_id",
    ["producer", "consumer.producer", "analysis.consumer.producer"],
)
def test_step_run_accepts_dot_separated_context_names(run_id):
    assert StepRun(run_id, ProducerStep(), {}).run_id == run_id


@pytest.mark.parametrize("run_id", ["consumer..producer", "consumer/producer"])
def test_step_run_rejects_malformed_context_names(run_id):
    with pytest.raises(ValueError, match="dot-separated names"):
        StepRun(run_id, ProducerStep(), {})


def test_step_run_requires_each_declared_input_binding():
    with pytest.raises(ValueError, match=r"missing: result; unexpected: none"):
        StepRun("consumer", ConsumerStep(), {})


def test_step_run_requires_the_steps_exact_input_declaration(tmp_path):
    copied_declaration = FileInput(
        "result",
        source=ProducerStep.result_output,
    )

    with pytest.raises(ValueError, match="does not use the declaration"):
        StepRun(
            "consumer",
            ConsumerStep(),
            {},
            inputs=(StepInputBinding(copied_declaration, tmp_path),),
        )


def test_step_run_output_must_belong_to_its_run():
    run = StepRun("other-producer", OtherProducerStep(), {})

    with pytest.raises(ValueError, match="does not belong to step"):
        StepRunOutput(run, ProducerStep.result_output)


def test_input_binding_requires_its_declared_source_output():
    other_run = StepRun("other-producer", OtherProducerStep(), {})

    with pytest.raises(ValueError, match="requires output 'producer.result'"):
        StepInputBinding(
            ConsumerStep.result_input,
            other_run.output(OtherProducerStep.result_output),
        )


def test_execution_plan_normalizes_collections_and_reused_output_paths(tmp_path):
    run = StepRun("producer", ProducerStep(), {})
    output = run.output(ProducerStep.result_output)
    relative_path = Path("reused/result.txt")

    plan = ExecutionPlan(
        goals=(run,),
        runs_to_execute=(),
        resolved_outputs={output: relative_path},
    )

    assert plan.goals == (run,)
    assert plan.runs_to_execute == ()
    assert plan.resolved_outputs == {output: relative_path.resolve()}
