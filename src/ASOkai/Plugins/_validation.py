"""Runtime contract checks for externally installed ASOkai plugins."""

from __future__ import annotations

import inspect

from ASOkai.Analysis import Analysis
from ASOkai._pipeline.base import Runnable
from ASOkai._pipeline.contracts.file_types import CsvFile, FileType
from ASOkai._pipeline.steps.analysis.base import AnalysisStep
from ASOkai._pipeline.steps.base import Step
from ASOkai._pipeline.tasks.base import Task
from ASOkai._pipeline.workflows.base import Workflow


def validate_plugin_instance(kind: str, instance: object) -> None:
    """Validate the declarations shared by one loaded plugin instance."""
    name = getattr(instance, "name", None)
    description = getattr(instance, "description", None)
    if type(name) is not str or not name.strip():
        raise TypeError(f"{kind} name must be a non-blank string.")
    if type(description) is not str or not description.strip():
        raise TypeError(f"{kind} description must be a non-blank string.")

    if isinstance(instance, Step):
        if type(instance).run_from_args is Step.run_from_args:
            raise TypeError("step must implement run_from_args().")
        instance.build_parser()
        if isinstance(instance, AnalysisStep):
            _validate_analysis_step(instance)
        return

    if isinstance(instance, Task):
        if type(instance.steps) is not list or not instance.steps:
            raise TypeError("task steps must be a non-empty list.")
        if any(not isinstance(step, Step) for step in instance.steps):
            raise TypeError("task steps must contain only Step instances.")
        return

    if isinstance(instance, Workflow):
        if type(instance.members) is not list or not instance.members:
            raise TypeError("workflow members must be a non-empty list.")
        if any(not isinstance(member, Runnable) for member in instance.members):
            raise TypeError(
                "workflow members must contain only runnable instances."
            )


def _validate_analysis_step(step: AnalysisStep) -> None:
    """Validate assumptions made by the shared analysis execution flow."""
    analysis_class = step.analysis_cls
    if (
        not inspect.isclass(analysis_class)
        or not issubclass(analysis_class, Analysis)
        or inspect.isabstract(analysis_class)
    ):
        raise TypeError("analysis_cls must be a concrete Analysis subclass.")
    if not step.spec.outputs:
        raise ValueError("an analysis step must declare a primary CSV output.")
    primary_output = step.spec.outputs[0]
    if not isinstance(primary_output.file_type, CsvFile):
        raise TypeError("an analysis step's first output must use CsvFile.")
    if len(primary_output.file_type.index) != 1:
        raise ValueError(
            "an analysis step's primary CSV output must declare exactly one index."
        )

    additional_outputs = step.spec.outputs[1:]
    if (
        additional_outputs
        and type(step).additional_output_values is AnalysisStep.additional_output_values
    ):
        raise TypeError(
            "an analysis step with additional outputs must implement "
            "additional_output_values()."
        )
    for output in additional_outputs:
        if type(output.file_type).write is FileType.write:
            raise TypeError(
                f"analysis output {output.name!r} must use a writable file contract."
            )


def validate_step_dependencies(
    step: Step,
    registered_steps: dict[str, Step],
) -> None:
    """Require inputs to use exact outputs from registered producer steps."""
    for file_input in step.spec.inputs:
        source = file_input.source
        producer = registered_steps.get(source.producer)
        if producer is None:
            raise ValueError(
                f"input {file_input.name!r} references unregistered producer "
                f"{source.producer!r}."
            )
        try:
            registered_output = producer.spec.output(source.name)
        except KeyError as error:
            raise ValueError(
                f"input {file_input.name!r} references unknown output "
                f"{source.name!r} from {source.producer!r}."
            ) from error
        if registered_output is not source:
            raise ValueError(
                f"input {file_input.name!r} must reuse the registered output "
                f"declaration {source.producer!r}/{source.name!r}."
            )


def _is_registered_step(
    step: Step,
    registered_steps: dict[str, Step],
) -> bool:
    registered = registered_steps.get(step.name)
    return registered is not None and type(registered) is type(step)


def validate_task_members(
    task: Task,
    registered_steps: dict[str, Step],
) -> None:
    """Require task members to match registered step implementations."""
    for step in task.steps:
        if not _is_registered_step(step, registered_steps):
            raise ValueError(
                f"step {step.name!r} is not registered through asokai.steps."
            )


def validate_workflow_members(
    workflow: Workflow,
    registered_steps: dict[str, Step],
    registered_tasks: dict[str, Task],
    registered_workflows: dict[str, Workflow],
    ancestors: frozenset[str] = frozenset(),
) -> None:
    """Require workflow members to match registered implementations."""
    if workflow.name in ancestors:
        raise ValueError(
            f"workflow {workflow.name!r} participates in a cycle."
        )
    ancestors = ancestors | {workflow.name}

    for member in workflow.members:
        if isinstance(member, Step):
            valid = _is_registered_step(member, registered_steps)
            group = "asokai.steps"
        elif isinstance(member, Task):
            registered = registered_tasks.get(member.name)
            valid = registered is not None and type(registered) is type(member)
            group = "asokai.tasks"
        elif isinstance(member, Workflow):
            registered = registered_workflows.get(member.name)
            valid = registered is not None and type(registered) is type(member)
            group = "asokai.workflows"
            if valid:
                validate_workflow_members(
                    member,
                    registered_steps,
                    registered_tasks,
                    registered_workflows,
                    ancestors,
                )
        else:
            valid = False
            group = "an ASOkai plugin entry point"
        if not valid:
            raise ValueError(
                f"member {member.name!r} is not registered through {group}."
            )
