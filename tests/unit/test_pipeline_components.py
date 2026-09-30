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

from ASOkai.Analysis import PerUnitAnalysis
from ASOkai._pipeline import catalog as pipeline_catalog
from ASOkai._pipeline.base import Runnable
from ASOkai._pipeline.contracts.file_types import (
    CsvFile,
    FastaFile,
    FileType,
    JsonFile,
)
from ASOkai._pipeline.contracts.files import FileInput, FileOutput
from ASOkai._pipeline.contracts.parameters import ScalarParam
from ASOkai._pipeline.contracts.run_spec import RunSpec
from ASOkai._pipeline.contracts.step_spec import StepSpec
from ASOkai._pipeline.steps.analysis.base import AnalysisStep
from ASOkai._pipeline.steps.base import ExternalCommandStep, Step
from ASOkai._pipeline.tasks.base import Task
from ASOkai._pipeline.validation import (
    validate_component,
    validate_step_dependencies,
    validate_workflow_members,
)


class ExampleAnalysis(PerUnitAnalysis):
    analysis_unit_type = "site"

    def analyze_unit(self, site):
        return [{"site_id": site.id, "value": 1}]


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


@pytest.mark.parametrize(
    ("failure", "message"),
    [
        ("duplicate", "duplicate run id"),
        ("unknown_run", "unknown run"),
        ("unknown_output", "unknown output"),
        ("unknown_input", "has no input"),
        ("incompatible", "cannot accept output"),
    ],
)
def test_named_task_runs_reject_invalid_local_links(failure, message):
    result = FileOutput("result", destination="consumer.txt")
    consumer_type = type(
        "_TaskConsumer",
        (Step,),
        {
            "name": "task-consumer",
            "description": "Consumes a task-local output.",
            "result_output": result,
            "spec": StepSpec(
                inputs=[FileInput("input", file_type=FileType())],
                outputs=[result],
            ),
            "run_from_args": lambda self, args: 0,
        },
    )
    producer = RegisteredProducerStep()
    consumer = consumer_type()
    producer_run = RunSpec("source", producer)
    input_name = "missing" if failure == "unknown_input" else "input"
    source_id = "missing" if failure == "unknown_run" else "source"
    output_name = "missing" if failure == "unknown_output" else "result"
    if failure == "incompatible":
        fasta_input = FileInput("input", file_type=FastaFile())
        fasta_result = FileOutput("result", destination="fasta-consumer.txt")
        incompatible_type = type(
            "_FastaTaskConsumer",
            (Step,),
            {
                "name": "fasta-task-consumer",
                "description": "Requires FASTA.",
                "result_output": fasta_result,
                "spec": StepSpec(inputs=[fasta_input], outputs=[fasta_result]),
                "run_from_args": lambda self, args: 0,
            },
        )
        consumer = incompatible_type()
    runs = (
        producer_run,
        RunSpec(
            "source" if failure == "duplicate" else "consumer",
            consumer,
            inputs={input_name: {"from_run": source_id, "output": output_name}},
        ),
    )
    task_type = type(
        "_InvalidTask",
        (Task,),
        {"name": "invalid-task", "description": "Invalid links.", "runs": runs},
    )

    with pytest.raises(ValueError, match=message):
        validate_component("task", task_type())


def test_named_task_runs_require_run_specs():
    task_type = type(
        "_MalformedTask",
        (Task,),
        {
            "name": "malformed-task",
            "description": "Invalid run.",
            "runs": ({"id": "source", "step": RegisteredProducerStep()},),
        },
    )

    with pytest.raises(TypeError, match="RunSpec"):
        validate_component("task", task_type())


@pytest.mark.parametrize(
    ("run_id", "step", "kwargs", "error", "message"),
    [
        ("bad name", RegisteredProducerStep(), {}, ValueError, "run_id"),
        ("source", object(), {}, TypeError, "step must be a Step"),
        (
            "source",
            RegisteredProducerStep(),
            {"parameters": []},
            TypeError,
            "parameters",
        ),
    ],
)
def test_run_spec_rejects_invalid_declarations(run_id, step, kwargs, error, message):
    with pytest.raises(error, match=message):
        RunSpec(run_id, step, **kwargs)


def test_task_run_rejects_invalid_fixed_parameter():
    result = FileOutput("result", destination="task-param.txt")
    step_type = type(
        "_TaskParameterStep",
        (Step,),
        {
            "name": "task-parameter-step",
            "description": "Receives a task run parameter.",
            "result_output": result,
            "spec": StepSpec(params=[ScalarParam("mode", str)], outputs=[result]),
            "run_from_args": lambda self, args: 0,
        },
    )
    task_type = type(
        "_InvalidParameterTask",
        (Task,),
        {
            "name": "invalid-parameter-task",
            "description": "Has an invalid fixed run parameter.",
            "runs": (RunSpec("run", step_type(), parameters={"mode": 21}),),
        },
    )

    with pytest.raises(ValueError, match="must be str"):
        validate_component("task", task_type())


def test_task_rejects_obsolete_parameter_declarations():
    task_type = type(
        "_OldTaskParameters",
        (Task,),
        {
            "name": "old-task-parameters",
            "description": "Uses removed task parameter declarations.",
            "params": (ScalarParam("mode", str),),
            "runs": (RunSpec("source", RegisteredProducerStep()),),
        },
    )

    with pytest.raises(ValueError, match="no longer supported"):
        validate_component("task", task_type())


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


def test_analysis_component_requires_declared_unit_type(monkeypatch):
    monkeypatch.setattr(ExampleAnalysis, "analysis_unit_type", "query")
    with pytest.raises(ValueError, match="analysis_unit_type"):
        validate_component("step", JsonPrimaryOutputStep())


def test_analysis_component_always_exposes_thread_count(monkeypatch):
    step = JsonPrimaryOutputStep()
    monkeypatch.setattr(step, "supports_multiple_threads", False)
    with pytest.raises(ValueError, match="n_threads resource"):
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
