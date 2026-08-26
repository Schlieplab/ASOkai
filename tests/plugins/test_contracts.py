#!/usr/bin/env python
"""Tests for contracts enforced on loaded plugin objects."""

from typing import ClassVar

import pytest

from ASOkai.Analysis import SiteSpecificAnalysis
from ASOkai.Plugins import (
    AnalysisStep,
    CsvFile,
    FileInput,
    FileOutput,
    FileType,
    JsonFile,
    Runnable,
    Step,
    StepSpec,
)
from ASOkai.Plugins._validation import (
    validate_plugin_instance,
    validate_step_dependencies,
    validate_workflow_members,
)


class ExampleAnalysis(SiteSpecificAnalysis):
    def analyze(self, site):
        return {"value": 1}


class InvalidNameTask:
    name = "invalid name"
    description = "Uses a name that cannot identify a pipeline task."
    steps: list[Step] = []


class MissingRunMethodStep(Step):
    name = "missing-run-method"
    description = "Does not implement the step execution method."
    spec = StepSpec()


class JsonPrimaryOutputStep(AnalysisStep):
    name = "json-primary-output"
    description = "Declares JSON as its primary analysis output."
    analysis_cls = ExampleAnalysis
    result_output = FileOutput(
        "result",
        destination="result.json",
        file_type=JsonFile(),
    )
    spec = StepSpec(outputs=[result_output])


class MissingAdditionalOutputValuesStep(AnalysisStep):
    name = "missing-additional-output-values"
    description = "Does not provide its additional output value."
    analysis_cls = ExampleAnalysis
    analysis_output = FileOutput(
        "analysis",
        destination="analysis.csv",
        file_type=CsvFile(
            index={"site_id": str},
            columns={"value": int},
        ),
    )
    summary_output = FileOutput(
        "summary",
        destination="summary.json",
        file_type=JsonFile(),
    )
    spec = StepSpec(outputs=[analysis_output, summary_output])


class OpaqueAdditionalOutputStep(MissingAdditionalOutputValuesStep):
    name = "opaque-additional-output"
    analysis_output = FileOutput(
        "analysis",
        destination="opaque-analysis.csv",
        file_type=CsvFile(
            index={"site_id": str},
            columns={"value": int},
        ),
    )
    opaque_output = FileOutput(
        "opaque",
        destination="opaque.bin",
        file_type=FileType(),
    )
    spec = StepSpec(
        outputs=[
            analysis_output,
            opaque_output,
        ],
    )

    def additional_output_values(self, analysis, results):
        return {self.opaque_output: b"value"}


class RegisteredProducerStep(Step):
    name = "producer"
    description = "Registered producer."
    result_output = FileOutput("result", destination="registered.txt")
    spec = StepSpec(outputs=[result_output])

    def run_from_args(self, args) -> int:
        return 0


class ShadowProducerStep(Step):
    name = "producer"
    description = "Different implementation using the registered name."
    result_output = FileOutput("result", destination="shadow.txt")
    spec = StepSpec(outputs=[result_output])

    def run_from_args(self, args) -> int:
        return 0


class ShadowConsumerStep(Step):
    name = "consumer"
    description = "References the shadow producer declaration."
    result_input = FileInput("result", source=ShadowProducerStep.result_output)
    spec = StepSpec(inputs=[result_input])

    def run_from_args(self, args) -> int:
        return 0


def test_plugin_name_must_be_usable_as_a_run_identifier():
    with pytest.raises(ValueError, match="letters, numbers, hyphens"):
        validate_plugin_instance("task", InvalidNameTask())


def test_step_plugin_must_implement_its_execution_method():
    with pytest.raises(TypeError, match="run_from_args"):
        validate_plugin_instance("step", MissingRunMethodStep())


def test_step_plugin_must_declare_an_output():
    class OutputlessStep(Step):
        name = "outputless"
        description = "Does not declare an output."
        spec = StepSpec()

        def run_from_args(self, args) -> int:
            return 0

    with pytest.raises(ValueError, match="at least one file output"):
        validate_plugin_instance("step", OutputlessStep())


@pytest.mark.parametrize(
    ("step", "message"),
    [
        (JsonPrimaryOutputStep(), "first output must use CsvFile"),
        (
            MissingAdditionalOutputValuesStep(),
            "must implement additional_output_values",
        ),
        (OpaqueAdditionalOutputStep(), "must use a writable file contract"),
    ],
)
def test_analysis_plugin_must_support_the_shared_execution_flow(step, message):
    with pytest.raises((TypeError, ValueError), match=message):
        validate_plugin_instance("analysis step", step)


def test_step_dependency_must_use_the_registered_output_declaration():
    with pytest.raises(ValueError, match="reuse the registered output"):
        validate_step_dependencies(
            ShadowConsumerStep(),
            {"producer": RegisteredProducerStep()},
        )


def test_plugin_workflow_cannot_contain_itself():
    class CyclicWorkflow:
        name: ClassVar[str] = "cyclic"
        description: ClassVar[str] = "Contains itself."
        members: list[Runnable] = []

    workflow = CyclicWorkflow()
    workflow.members = [workflow]

    with pytest.raises(ValueError, match="participates in a cycle"):
        validate_workflow_members(
            workflow,
            registered_steps={},
            registered_tasks={},
            registered_workflows={workflow.name: workflow},
        )
