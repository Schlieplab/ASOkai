#!/usr/bin/env python
"""
Filename: tests/unit/test_execution_contracts.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Tests for concrete step-run and execution-plan contracts.
License: LGPL-3.0-or-later
"""

from pathlib import Path

import pytest

from ASOkai.Plugins import (
    FileInput,
    FileOutput,
    FileType,
    InputConfigField,
    OutputPathTemplate,
    ScalarParam,
    Step,
    StepSpec,
    TemplateField,
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


def test_step_runs_with_the_same_id_remain_distinct_objects():
    first = StepRun("producer", ProducerStep(), {})
    second = StepRun("producer", ProducerStep(), {})

    assert first != second
    assert len({first, second}) == 2


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


def test_external_input_keeps_shared_config_beside_scoped_producer(tmp_path):
    producer_output = FileOutput(
        "result",
        destination=OutputPathTemplate(
            "producer/{mode}.txt",
            fields={"mode": TemplateField("producer.mode")},
        ),
    )

    class ConfiguredProducer(Step):
        name = "configured-producer"
        description = ""
        result_output = producer_output
        spec = StepSpec(
            params=[ScalarParam("mode", str, config="producer.mode")],
            outputs=[producer_output],
        )

    selected_input = FileInput("result", source=producer_output)
    file_input = FileInput("external", file_type=FileType())
    result_output = FileOutput(
        "summary",
        destination=OutputPathTemplate(
            "summaries/{mode}.txt",
            fields={"mode": InputConfigField("external", "producer.mode")},
        ),
    )

    class MixedConsumer(Step):
        name = "mixed-consumer"
        description = ""
        result_input = selected_input
        external_input = file_input
        summary_output = result_output
        spec = StepSpec(inputs=[selected_input, file_input], outputs=[result_output])

    config = {"datadir": str(tmp_path), "producer": {"mode": "main"}}
    producer = StepRun(
        "configured-producer",
        ConfiguredProducer(),
        config,
        parameters={"mode": "alternate"},
    )
    consumer = StepRun(
        "mixed-consumer",
        MixedConsumer(),
        config,
        inputs=(
            StepInputBinding(selected_input, producer.output(producer_output)),
            StepInputBinding(file_input, tmp_path / "external.txt"),
        ),
    )

    assert consumer.config["producer"]["mode"] == "alternate"
    assert consumer.input_configurations()["external"]["producer"]["mode"] == "main"
    assert consumer.output_paths()["summary"] == tmp_path / "summaries/main.txt"


def test_external_input_uses_consumer_parameter_default(tmp_path):
    file_input = FileInput("external", file_type=FileType())
    result_output = FileOutput(
        "summary",
        destination=OutputPathTemplate(
            "summaries/{mode}.txt",
            fields={"mode": InputConfigField("external", "producer.mode")},
        ),
    )

    class DefaultedConsumer(Step):
        name = "defaulted-consumer"
        description = ""
        external_input = file_input
        summary_output = result_output
        spec = StepSpec(
            inputs=[file_input],
            params=[
                ScalarParam("mode", str, config="producer.mode", default="default")
            ],
            outputs=[result_output],
        )

    run = StepRun(
        "defaulted-consumer",
        DefaultedConsumer(),
        {"datadir": str(tmp_path)},
        inputs=(StepInputBinding(file_input, tmp_path / "external.txt"),),
    )

    assert run.output_paths()["summary"] == tmp_path / "summaries/default.txt"


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
