#!/usr/bin/env python
"""
Filename: tests/integration/test_pipeline_execution.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: End-to-end coverage for planning, CWL execution, and publication.
License: LGPL-3.0-or-later
"""

from pathlib import Path
import shutil

import pytest

from ASOkai.Plugins import FileInput, FileOutput, Step, StepSpec
from ASOkai._cwl.executors import CwlToolExecutor, ToilExecutor
from ASOkai._pipeline.runner import run_all


producer_output = FileOutput(
    "result",
    destination="producer/result.txt",
)


class ProducerStep(Step):
    name = "integration-producer"
    description = "Writes one synthetic producer result."
    result_output = producer_output
    spec = StepSpec(
        base_command=["sh", "-c", "printf producer > result.txt"],
        outputs=[result_output],
    )


def _consumer_step(name: str) -> Step:
    producer_input = FileInput(
        "producer_result",
        source=producer_output,
    )
    result_output = FileOutput(
        "result",
        destination=f"consumers/{name}.txt",
    )
    step_type = type(
        f"_{name.replace('-', '_').title()}Step",
        (Step,),
        {
            "name": name,
            "description": f"Writes the synthetic {name} result.",
            "producer_input": producer_input,
            "result_output": result_output,
            "spec": StepSpec(
                base_command=[
                    "sh",
                    "-c",
                    f"printf {name} > {name}.txt",
                ],
                inputs=[producer_input],
                outputs=[result_output],
            ),
        },
    )
    return step_type()


@pytest.mark.integration
@pytest.mark.skipif(
    shutil.which("ASOkai") is None,
    reason="the ASOkai executable is required",
)
@pytest.mark.parametrize(
    "executor",
    [
        pytest.param(
            CwlToolExecutor(extra_args=["--no-container"]),
            marks=pytest.mark.skipif(
                shutil.which("cwltool") is None,
                reason="cwltool is required",
            ),
            id="cwltool",
        ),
        pytest.param(
            ToilExecutor(
                extra_args=["--no-container", "--clean", "always"],
                capture_worker_output=True,
            ),
            marks=pytest.mark.skipif(
                shutil.which("toil-cwl-runner") is None,
                reason="toil-cwl-runner is required",
            ),
            id="toil",
        ),
    ],
)
def test_shared_producer_executes_once_and_outputs_are_published(
    tmp_path,
    executor,
):
    producer = ProducerStep()
    first = _consumer_step("first-consumer")
    second = _consumer_step("second-consumer")
    registry = {
        step.name: step
        for step in (producer, first, second)
    }
    stale_output = tmp_path / "consumers/first-consumer.txt"
    stale_output.parent.mkdir(parents=True)
    stale_output.write_text("stale", encoding="utf-8")
    unrelated = tmp_path / "unrelated/keep.txt"
    unrelated.parent.mkdir(parents=True)
    unrelated.write_text("keep", encoding="utf-8")

    outputs = run_all(
        [first, second],
        {"datadir": str(tmp_path)},
        force=True,
        executor=executor,
        registered_steps=registry,
    )

    assert outputs == {
        "first-consumer.result": tmp_path / "consumers/first-consumer.txt",
        "second-consumer.result": tmp_path / "consumers/second-consumer.txt",
    }
    assert (tmp_path / "producer/result.txt").read_text() == "producer"
    assert outputs["first-consumer.result"].read_text() == "first-consumer"
    assert outputs["second-consumer.result"].read_text() == "second-consumer"
    assert unrelated.read_text(encoding="utf-8") == "keep"

    run_cwl = next((tmp_path / "jobs").glob("asokai-job-*/run.cwl"))
    assert run_cwl.read_text().count("step_integration_producer:") == 1
