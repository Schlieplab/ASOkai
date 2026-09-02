#!/usr/bin/env python
"""Tests for concrete step-run and execution-plan contracts."""

from pathlib import Path

import pytest

from ASOkai.Plugins import (
    FileInput,
    FileOutput,
    InputConfigField,
    OutputPathTemplate,
    Step,
    StepSpec,
)
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


class InputConfiguredConsumerStep(Step):
    name = "input-configured-consumer"
    description = "Name an output from the selected producer configuration."
    result_input = FileInput("result", source=ProducerStep.result_output)
    summary_output = FileOutput(
        "summary",
        destination=OutputPathTemplate(
            "summaries/{producer_mode}_summary.txt",
            fields={
                "producer_mode": InputConfigField(
                    "result",
                    "producer.mode",
                )
            },
        ),
    )
    spec = StepSpec(
        inputs=[result_input],
        outputs=[summary_output],
    )


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


def test_step_run_uses_the_selected_producer_configuration(tmp_path):
    producer_config = {
        "datadir": str(tmp_path),
        "producer": {"mode": "alternate"},
    }
    consumer_config = {
        "datadir": str(tmp_path),
        "producer": {"mode": "main"},
    }
    producer_run = StepRun("producer", ProducerStep(), producer_config)
    consumer_run = StepRun(
        "input-configured-consumer",
        InputConfiguredConsumerStep(),
        consumer_config,
        inputs=(
            StepInputBinding(
                InputConfiguredConsumerStep.result_input,
                producer_run.output(ProducerStep.result_output),
            ),
        ),
    )

    assert consumer_run.input_paths() == {
        "result": tmp_path / "result.txt",
    }
    assert consumer_run.output_paths() == {
        "summary": tmp_path / "summaries/alternate_summary.txt",
    }


def test_path_override_uses_main_config_not_the_filename(tmp_path):
    selected_input = tmp_path / "filename-must-not-affect-output.json"
    run = StepRun(
        "input-configured-consumer",
        InputConfiguredConsumerStep(),
        {
            "datadir": str(tmp_path),
            "producer": {"mode": "main"},
        },
        inputs=(
            StepInputBinding(
                InputConfiguredConsumerStep.result_input,
                selected_input,
            ),
        ),
    )

    assert run.output_paths() == {
        "summary": tmp_path / "summaries/main_summary.txt",
    }


def test_step_run_validates_and_cleans_its_declared_outputs(tmp_path):
    run = StepRun(
        "producer",
        ProducerStep(),
        {"datadir": str(tmp_path)},
    )
    output_path = run.output_paths()["result"]

    with pytest.raises(FileNotFoundError, match="producer/result"):
        run.validate_output_files()

    output_path.write_text("result")
    assert run.validate_output_files() == {"result": output_path}

    run.cleanup_output_files()
    assert not output_path.exists()


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
