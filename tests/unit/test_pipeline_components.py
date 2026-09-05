#!/usr/bin/env python
"""
Filename: tests/unit/test_pipeline_components.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Tests for shared pipeline-component validation contracts.
License: LGPL-3.0-or-later
"""

from typing import ClassVar

import pytest

from ASOkai.Analysis import SiteSpecificAnalysis
from ASOkai._pipeline import catalog as pipeline_catalog
from ASOkai._pipeline.base import Runnable
from ASOkai._pipeline.contracts.file_types import CsvFile, FileType, JsonFile
from ASOkai._pipeline.contracts.files import FileInput, FileOutput
from ASOkai._pipeline.contracts.step_spec import StepSpec
from ASOkai._pipeline.steps.analysis.base import AnalysisStep
from ASOkai._pipeline.steps.base import ExternalCommandStep, Step
from ASOkai._pipeline.validation import (
    validate_component,
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


def test_component_name_must_be_usable_as_a_run_identifier():
    with pytest.raises(ValueError, match="letters, numbers, hyphens"):
        validate_component("task", InvalidNameTask())


def test_component_must_implement_the_requested_contract():
    class NamedObject:
        name = "named-object"
        description = "Has identity but no pipeline behavior."

    with pytest.raises(TypeError, match="Step contract.*NamedObject"):
        validate_component("step", NamedObject())


def test_step_cannot_be_validated_as_a_task_through_structural_overlap():
    class StepThatLooksLikeTask(RegisteredProducerStep):
        steps: tuple[Step, ...] = ()

    with pytest.raises(TypeError, match="only the Task contract"):
        validate_component("task", StepThatLooksLikeTask())


def test_builtin_declaration_errors_identify_the_component_as_builtin():
    class InvalidBuiltinTask:
        name = "invalid-builtin-task"
        description = "Contains a value that is not a step."
        steps = (object(),)

    with pytest.raises(
        ValueError,
        match=r"Invalid built-in ASOkai task.*only Step instances",
    ):
        pipeline_catalog._validate_builtin_declarations(
            "task",
            (InvalidBuiltinTask(),),
        )


def test_step_component_must_implement_its_execution_method():
    with pytest.raises(TypeError, match="run_from_args"):
        validate_component("step", MissingRunMethodStep())


def test_external_step_component_must_build_its_command():
    class MissingCommandStep(ExternalCommandStep):
        name = "missing-command"
        description = "Does not implement the external command hook."
        result_output = FileOutput("result", destination="result.txt")
        spec = StepSpec(outputs=[result_output])

    with pytest.raises(TypeError, match="must implement build_command"):
        validate_component("step", MissingCommandStep())


def test_step_component_must_declare_an_output():
    class OutputlessStep(Step):
        name = "outputless"
        description = "Does not declare an output."
        spec = StepSpec()

        def run_from_args(self, args) -> int:
            return 0

    with pytest.raises(ValueError, match="at least one file output"):
        validate_component("step", OutputlessStep())


@pytest.mark.parametrize("cache_version", [0, -1, True, "1"])
def test_step_cache_version_must_be_a_positive_integer(cache_version):
    output = FileOutput("result", destination="result.txt")

    with pytest.raises(TypeError, match="cache_version must be a positive integer"):
        type(
            "InvalidCacheVersionStep",
            (Step,),
            {
                "name": "invalid-cache-version",
                "description": "Declares an invalid cache version.",
                "cache_version": cache_version,
                "result_output": output,
                "spec": StepSpec(outputs=[output]),
            },
        )


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
def test_analysis_component_must_support_the_shared_execution_flow(step, message):
    with pytest.raises((TypeError, ValueError), match=message):
        validate_component("step", step)


def test_step_dependency_must_use_the_registered_output_declaration():
    with pytest.raises(ValueError, match="reuse the registered output"):
        validate_step_dependencies(
            ShadowConsumerStep(),
            {"producer": RegisteredProducerStep()},
        )


def test_workflow_component_cannot_contain_itself():
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


def test_workflow_validates_the_actual_steps_of_a_registered_task():
    registered_step = RegisteredProducerStep()

    class RegisteredTask:
        name = "registered-task"
        description = "A registered task."
        steps = (registered_step,)

    task_member = RegisteredTask()
    task_member.steps = (ShadowProducerStep(),)

    class TaskWorkflow:
        name = "task-workflow"
        description = "Contains a separately instantiated registered task."
        members = (task_member,)

    workflow = TaskWorkflow()

    with pytest.raises(ValueError, match="not registered in the step catalog"):
        validate_workflow_members(
            workflow,
            registered_steps={registered_step.name: registered_step},
            registered_tasks={RegisteredTask.name: RegisteredTask()},
            registered_workflows={workflow.name: workflow},
        )
