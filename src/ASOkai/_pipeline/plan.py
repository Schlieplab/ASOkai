#!/usr/bin/env python
"""
Filename: src/ASOkai/_pipeline/plan.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Goal-driven resolution of concrete pipeline step runs.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

import logging
from collections import deque
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from ASOkai.Types import Scalar
from ASOkai._pipeline import config as cfg
from ASOkai._pipeline.base import Runnable, flatten_workflow_members
from ASOkai._pipeline.contracts.execution import (
    ExecutionPlan,
    StepInputBinding,
    StepRun,
    StepRunOutput,
)
from ASOkai._pipeline.contracts.files import FileInput, FileOutput
from ASOkai._pipeline.output_receipts import reusable_output_paths
from ASOkai._pipeline.steps.base import Step
from ASOkai._pipeline.tasks.base import (
    Task,
    validate_task_parameters,
    validate_task_runs,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _RunOutputReference:
    """An input link to the output of a named run."""

    request_id: str
    output_name: str


@dataclass(frozen=True)
class _ExplicitInput:
    """An input selection and its declaration location."""

    source: Path | _RunOutputReference
    location: str


@dataclass(frozen=True)
class _GoalRequest:
    """One normalized goal before dependency discovery."""

    request_id: str
    step: Step
    parameters: Mapping[str, Any] = field(default_factory=dict)
    input_selections: Mapping[str, _ExplicitInput] = field(default_factory=dict)


@dataclass(frozen=True)
class _RequestedInputSource:
    """The path override or producer request found for one file input."""

    file_input: FileInput
    source: Path | _RunRequest
    output: FileOutput | None = None
    selection_path: str | None = None


@dataclass
class _RunRequest:
    """One run requested during breadth-first dependency discovery."""

    request_id: str
    step: Step
    config: dict[str, Any]
    dependency_path: tuple[str, ...]
    parameters: dict[str, Any] = field(default_factory=dict)
    input_selections: dict[str, _ExplicitInput] = field(default_factory=dict)
    input_sources: list[_RequestedInputSource] = field(default_factory=list)


@dataclass(frozen=True)
class _RunSignature:
    """Resolved values that determine whether requests can share one run."""

    step_name: str
    parameter_values: tuple[tuple[str, Scalar], ...]
    input_sources: tuple[tuple[str, Path | StepRunOutput], ...]


def _request_matches_step_config(
    request: _RunRequest,
    step: Step,
    config: Mapping[str, Any],
    parameters: Mapping[str, Any] | None = None,
    input_selections: Mapping[str, _ExplicitInput] | None = None,
) -> bool:
    """Return whether an existing request describes this step configuration."""
    return (
        type(request.step) is type(step)
        and request.config == config
        and request.parameters == (parameters or {})
        and request.input_selections == (input_selections or {})
    )


def _configured_producer_request_id(
    consumer_request_id: str,
    producer_step_name: str,
    *,
    input_name: str | None = None,
) -> str:
    """Return the contextual ID for a parameter-configured producer request."""
    context = consumer_request_id
    if input_name is not None:
        context = f"{context}.{input_name}"
    return f"{context}.{producer_step_name}"


def _run_signature(
    request: _RunRequest,
    input_bindings: Sequence[StepInputBinding],
) -> _RunSignature:
    """Return the result-affecting signature of one producer-ready request."""
    return _RunSignature(
        step_name=request.step.name,
        parameter_values=tuple(
            request.step.resolved_parameter_values(
                request.config, request.parameters
            ).items()
        ),
        input_sources=tuple(
            (binding.file_input.name, binding.source) for binding in input_bindings
        ),
    )


def _validate_unique_output_paths(runs: Sequence[StepRun]) -> None:
    """Reject distinct outputs that would publish to the same path."""
    owners: dict[Path, str] = {}
    for run in runs:
        for output in run.step.spec.outputs:
            path = run.output_path(output).resolve()
            qualified_name = f"{run.run_id}.{output.name}"
            previous = owners.get(path)
            if previous is not None:
                raise ValueError(
                    f"Output path collision: '{previous}' and "
                    f"'{qualified_name}' both write to {path}."
                )
            owners[path] = qualified_name


class _PlanBuilder:
    """Discover run requests breadth-first, then resolve them producer-first."""

    def __init__(
        self,
        main_config: dict,
        registered_steps: Mapping[str, Step],
        *,
        non_recursive: bool,
        force: bool,
        validate_input_files: bool = True,
        output_validation_mode: cfg.OutputValidationMode = "signature",
    ) -> None:
        self.main_config = main_config
        self.registered_steps = registered_steps
        self.non_recursive = non_recursive
        self.force_goal_runs = force
        self.validate_input_files = validate_input_files
        self.output_validation_mode = output_validation_mode
        self.requests: dict[str, _RunRequest] = {}
        self.pending_request_ids: deque[str] = deque()

    def _registered_producer(
        self,
        consumer_step: Step,
        file_input: FileInput,
    ) -> Step:
        """Return and validate the registered producer for one file input."""
        source = file_input.source
        assert source is not None
        producer = self.registered_steps.get(source.producer)
        if producer is None:
            raise ValueError(
                f"Step '{consumer_step.name}' references unknown producer "
                f"'{source.producer}'."
            )
        try:
            declared = producer.spec.output(source.name)
        except KeyError as error:
            raise ValueError(
                f"Step '{consumer_step.name}' input "
                f"'{file_input.name}' references "
                f"unknown output '{source.name}' on step '{source.producer}'."
            ) from error
        if declared is not source:
            raise ValueError(
                f"Step '{consumer_step.name}' input "
                f"'{file_input.name}' references "
                f"an output declaration that does not belong to "
                f"'{source.producer}'."
            )
        return producer

    def _existing_output_paths(self, run: StepRun) -> dict[str, Path] | None:
        """Return reusable outputs, or ``None`` when the run is required."""
        if self.output_validation_mode == "contract":
            try:
                paths = run.validate_output_files()
            except (OSError, UnicodeError, TypeError, ValueError):
                return None
            logger.debug(
                "[plan] '%s' outputs passed full file validation — reused.",
                run.run_id,
            )
            return paths

        paths = reusable_output_paths(run)
        if paths is None:
            return None
        logger.debug(
            "[plan] '%s' outputs match their validation receipt — reused.",
            run.run_id,
        )
        return paths

    def _producer_config_with_overrides(
        self,
        file_input: FileInput,
        producer_parameter_overrides: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Return main configuration with one input's producer overrides."""
        overrides: dict[str, Any] = {}
        for name, value in producer_parameter_overrides.items():
            parameter = file_input.configurable_parameter(name)
            assert parameter.config is not None
            overrides[parameter.config] = value
        return cfg.apply_overrides(deepcopy(self.main_config), overrides)

    def _reserve_request(
        self,
        request_id: str,
        step: Step,
        config: dict[str, Any],
        *,
        dependency_path: tuple[str, ...],
        parameters: Mapping[str, Any] | None = None,
        input_selections: Mapping[str, _ExplicitInput] | None = None,
    ) -> _RunRequest:
        """Reserve one request in the breadth-first discovery queue."""
        step.validate_output_declaration()
        existing_request = self.requests.get(request_id)
        if existing_request is not None:
            if not _request_matches_step_config(
                existing_request,
                step,
                config,
                parameters,
                input_selections,
            ):
                raise ValueError(
                    f"Request id '{request_id}' resolves to conflicting step "
                    "configurations."
                )
            return existing_request

        request = _RunRequest(
            request_id=request_id,
            step=step,
            config=config,
            dependency_path=dependency_path,
            parameters=dict(parameters or {}),
            input_selections=dict(input_selections or {}),
        )
        self.requests[request_id] = request
        self.pending_request_ids.append(request_id)
        return request

    def _discover_input_source(
        self,
        consumer_request: _RunRequest,
        file_input: FileInput,
    ) -> _RequestedInputSource:
        """Resolve one override or discover its producer request."""
        explicit = consumer_request.input_selections.get(file_input.name)
        if explicit is not None:
            if isinstance(explicit.source, Path):
                return _RequestedInputSource(
                    file_input=file_input,
                    source=explicit.source,
                    selection_path=f"{explicit.location}.path",
                )
            producer_request = self.requests[explicit.source.request_id]
            try:
                output = producer_request.step.spec.output(
                    explicit.source.output_name
                )
            except KeyError as error:
                raise ValueError(
                    f"{explicit.location}.output: run "
                    f"'{producer_request.request_id}' has no output "
                    f"'{explicit.source.output_name}'."
                ) from error
            if not file_input.accepts_output(output):
                raise ValueError(
                    f"{explicit.location}: output '{output.name}' from "
                    f"'{producer_request.request_id}' is incompatible with "
                    f"input '{file_input.name}'."
                )
            return _RequestedInputSource(
                file_input=file_input,
                source=producer_request,
                output=output,
                selection_path=explicit.location,
            )

        path_override = file_input.configured_path_override(
            consumer_request.config,
            consumer_request.step.name,
        )
        if path_override is not None:
            return _RequestedInputSource(
                file_input=file_input,
                source=path_override,
            )

        if file_input.source is None:
            raise ValueError(
                f"Run '{consumer_request.request_id}' input '{file_input.name}' "
                "requires a path or a named producer run."
            )

        producer = self._registered_producer(consumer_request.step, file_input)
        if producer.name in consumer_request.dependency_path:
            cycle = " -> ".join((*consumer_request.dependency_path, producer.name))
            raise ValueError(f"Dependency cycle detected: {cycle}.")

        producer_parameter_overrides = file_input.configured_parameters(
            consumer_request.config,
            consumer_request.step.name,
        )
        if producer_parameter_overrides is None:
            producer_request_id = producer.name
            producer_config = self.main_config
            producer_dependency_path = (producer.name,)
        else:
            producer_request_id = _configured_producer_request_id(
                consumer_request.request_id,
                producer.name,
            )
            producer_config = self._producer_config_with_overrides(
                file_input,
                producer_parameter_overrides,
            )
            existing_request = self.requests.get(producer_request_id)
            if existing_request is not None and not _request_matches_step_config(
                existing_request,
                producer,
                producer_config,
            ):
                producer_request_id = _configured_producer_request_id(
                    consumer_request.request_id,
                    producer.name,
                    input_name=file_input.name,
                )
            producer_dependency_path = (
                *consumer_request.dependency_path,
                producer.name,
            )

        producer_request = self._reserve_request(
            producer_request_id,
            producer,
            producer_config,
            dependency_path=producer_dependency_path,
        )
        return _RequestedInputSource(
            file_input=file_input,
            source=producer_request,
            output=file_input.source,
        )

    def _discover_run_requests(self) -> None:
        """Resolve queued requests and add their producers breadth-first."""
        while self.pending_request_ids:
            request = self.requests[self.pending_request_ids.popleft()]
            request.input_sources.extend(
                self._discover_input_source(request, file_input)
                for file_input in request.step.spec.inputs
            )

    def _validate_run(self, run: StepRun) -> None:
        """Validate one concrete run when its configuration is required."""
        selected_inputs = {
            binding.file_input.name
            for binding in run.inputs
            if binding.selection_path is not None
        }
        cfg.validate_step_config(
            run.config,
            [run.step],
            validate_input_files=self.validate_input_files,
            parameters=run.parameters,
            skip_input_names=selected_inputs,
        )
        if self.validate_input_files:
            for binding in run.inputs:
                if binding.selection_path is not None and isinstance(
                    binding.source, Path
                ):
                    cfg.validate_file_input_path(
                        binding.file_input,
                        binding.source,
                        binding.selection_path,
                    )

    def _producer_first_requests(self) -> list[_RunRequest]:
        """Return discovered requests with producers before consumers."""
        remaining_request_ids = list(self.requests)
        resolved_request_ids: set[str] = set()
        ordered_requests: list[_RunRequest] = []

        while remaining_request_ids:
            ready_request_ids = [
                request_id
                for request_id in remaining_request_ids
                if all(
                    isinstance(input_source.source, Path)
                    or input_source.source.request_id in resolved_request_ids
                    for input_source in self.requests[request_id].input_sources
                )
            ]
            if not ready_request_ids:
                cycle = ", ".join(remaining_request_ids)
                raise ValueError(
                    f"Dependency cycle detected involving run(s): {cycle}."
                )

            ordered_requests.extend(
                self.requests[request_id] for request_id in ready_request_ids
            )
            resolved_request_ids.update(ready_request_ids)
            remaining_request_ids = [
                request_id
                for request_id in remaining_request_ids
                if request_id not in resolved_request_ids
            ]

        return ordered_requests

    def _resolve_run_requests(
        self,
    ) -> tuple[dict[str, StepRun], tuple[StepRun, ...]]:
        """Resolve producer-first requests into shared concrete runs."""
        run_by_request_id: dict[str, StepRun] = {}
        run_by_signature: dict[_RunSignature, StepRun] = {}
        producer_first_runs: list[StepRun] = []

        for request in self._producer_first_requests():
            input_bindings: list[StepInputBinding] = []
            for input_source in request.input_sources:
                source = input_source.source
                if isinstance(source, Path):
                    input_bindings.append(
                        StepInputBinding(
                            input_source.file_input,
                            source,
                            selection_path=input_source.selection_path,
                        )
                    )
                    continue
                producer_run = run_by_request_id[source.request_id]
                assert input_source.output is not None
                input_bindings.append(
                    StepInputBinding(
                        input_source.file_input,
                        producer_run.output(input_source.output),
                        selection_path=input_source.selection_path,
                    )
                )

            run_signature = _run_signature(request, input_bindings)
            run = run_by_signature.get(run_signature)
            if run is None:
                run = StepRun(
                    run_id=request.request_id,
                    step=request.step,
                    config=request.config,
                    inputs=tuple(input_bindings),
                    parameters=request.parameters,
                )
                run_by_signature[run_signature] = run
                producer_first_runs.append(run)
            run_by_request_id[request.request_id] = run
        return run_by_request_id, tuple(producer_first_runs)

    def _schedule_required_runs(
        self,
        goals: tuple[StepRun, ...],
        producer_first_runs: tuple[StepRun, ...],
    ) -> tuple[tuple[StepRun, ...], dict[StepRunOutput, Path]]:
        """Select missing runs reachable through goals that cannot be reused."""
        goal_runs = set(goals)
        pending_required_runs = deque(goals)
        checked_runs: set[StepRun] = set()
        runs_to_execute: set[StepRun] = set()
        reusable_outputs: dict[StepRunOutput, Path] = {}

        while pending_required_runs:
            run = pending_required_runs.popleft()
            if run in checked_runs:
                continue
            checked_runs.add(run)
            self._validate_run(run)

            existing_outputs = None
            if not (self.force_goal_runs and run in goal_runs):
                existing_outputs = self._existing_output_paths(run)
            if existing_outputs is not None:
                for output in run.step.spec.outputs:
                    reusable_outputs[run.output(output)] = existing_outputs[output.name]
                continue

            if self.non_recursive and run not in goal_runs:
                raise RuntimeError(
                    f"Run '{run.run_id}' is required, but its outputs are "
                    "missing or invalid. Omit --non-recursive to run missing "
                    "dependencies automatically."
                )

            runs_to_execute.add(run)
            for input_binding in run.inputs:
                source = input_binding.source
                if isinstance(source, StepRunOutput):
                    pending_required_runs.append(source.run)

        ordered_runs_to_execute = tuple(
            run for run in producer_first_runs if run in runs_to_execute
        )
        return ordered_runs_to_execute, reusable_outputs

    def build(
        self, goal_requests: list[_GoalRequest]
    ) -> ExecutionPlan:
        """Resolve reserved main goals into a dependency-complete plan."""
        goals, producer_first_runs = self._resolve_goals(goal_requests)
        runs_to_execute, reusable_outputs = self._schedule_required_runs(
            goals,
            producer_first_runs,
        )
        active_runs = set(runs_to_execute)
        active_runs.update(output.run for output in reusable_outputs)
        _validate_unique_output_paths(
            tuple(run for run in producer_first_runs if run in active_runs)
        )

        return ExecutionPlan(
            goals=goals,
            runs_to_execute=runs_to_execute,
            resolved_outputs=reusable_outputs,
        )

    def _resolve_goals(
        self,
        goal_requests: list[_GoalRequest],
    ) -> tuple[tuple[StepRun, ...], tuple[StepRun, ...]]:
        """Discover dependencies and return goals plus producer-first runs."""
        for goal in goal_requests:
            self._reserve_request(
                goal.request_id,
                goal.step,
                self.main_config,
                dependency_path=(goal.step.name,),
                parameters=goal.parameters,
                input_selections=goal.input_selections,
            )
        self._discover_run_requests()

        run_by_request_id, producer_first_runs = self._resolve_run_requests()
        goals = tuple(run_by_request_id[goal.request_id] for goal in goal_requests)
        return goals, producer_first_runs

    def build_export(
        self,
        goal_requests: list[_GoalRequest],
        *,
        recursive: bool,
    ) -> ExecutionPlan:
        """Resolve runs for export without consulting existing output files."""
        goals, producer_first_runs = self._resolve_goals(goal_requests)
        for run in producer_first_runs:
            self._validate_run(run)

        goal_runs = set(goals)
        included_runs = (
            producer_first_runs
            if recursive
            else tuple(run for run in producer_first_runs if run in goal_runs)
        )
        _validate_unique_output_paths(included_runs)
        included_run_set = set(included_runs)
        external_outputs: dict[StepRunOutput, Path] = {}
        for run in included_runs:
            for binding in run.inputs:
                source = binding.source
                if (
                    isinstance(source, StepRunOutput)
                    and source.run not in included_run_set
                ):
                    external_outputs[source] = source.run.output_path(
                        source.output
                    )

        return ExecutionPlan(
            goals=goals,
            runs_to_execute=included_runs,
            resolved_outputs=external_outputs,
        )


def _declared_input_selections(
    step: Step,
    declarations: Mapping[str, Any],
    named_run_ids: Mapping[str, str],
    location_prefix: str,
) -> dict[str, _ExplicitInput]:
    """Normalize selected inputs from YAML or a task declaration."""
    selections: dict[str, _ExplicitInput] = {}
    declared_inputs = {file_input.name for file_input in step.spec.inputs}
    for name, declaration in declarations.items():
        location = f"{location_prefix}.inputs.{name}"
        if name not in declared_inputs:
            raise ValueError(
                f"{location}: step '{step.name}' has no input with this name."
            )
        if "path" in declaration:
            selections[name] = _ExplicitInput(
                Path(declaration["path"]).resolve(), location
            )
            continue
        run_id = declaration["run_id"]
        request_id = named_run_ids.get(run_id)
        if request_id is None:
            raise ValueError(f"{location}.run_id: unknown named run '{run_id}'.")
        selections[name] = _ExplicitInput(
            _RunOutputReference(request_id, declaration["output"]),
            location,
        )
    return selections


def _resolved_task_parameters(
    task: Task,
    config: Mapping[str, Any],
    overrides: Mapping[str, Any],
    location: str,
) -> dict[str, Any]:
    """Resolve one task selection's declared scalar parameters."""
    if not isinstance(overrides, Mapping):
        raise TypeError(f"{location}.parameters must be a mapping.")
    declarations = validate_task_parameters(task)
    unknown = set(overrides) - {parameter.name for parameter in declarations}
    if unknown:
        names = ", ".join(sorted(str(name) for name in unknown))
        raise ValueError(f"{location}.parameters has unknown parameter(s): {names}.")

    values: dict[str, Any] = {}
    for parameter in declarations:
        try:
            if parameter.name in overrides:
                value = cfg.resolve_parameter_value(
                    config, parameter, override=overrides[parameter.name]
                )
            else:
                value = cfg.resolve_parameter_value(config, parameter)
        except KeyError as error:
            raise ValueError(
                f"{location}.parameters.{parameter.name}: requires a value."
            ) from error
        try:
            parameter.validate(value)
        except (TypeError, ValueError) as error:
            raise ValueError(
                f"{location}.parameters.{parameter.name}: {error}"
            ) from error
        values[parameter.name] = value
    return values


def _task_goal_requests(
    task: Task,
    prefix: str | None,
    config: Mapping[str, Any],
    parameters: Mapping[str, Any] | None = None,
    *,
    location: str | None = None,
) -> list[_GoalRequest]:
    """Normalize steps or named task runs into step-run requests."""
    selection_location = location or f"task[{task.name}]"
    values = _resolved_task_parameters(
        task, config, parameters if parameters is not None else {}, selection_location
    )
    if not hasattr(task, "runs"):
        if values:
            raise ValueError("task params require named runs for forwarding.")
        return [
            _GoalRequest(f"{prefix}.{step.name}" if prefix else step.name, step)
            for step in task.steps
        ]

    runs = validate_task_runs(task)
    context = prefix or task.name
    named_run_ids = {run["id"]: f"{context}.{run['id']}" for run in runs}
    return [
        _GoalRequest(
            request_id=named_run_ids[run["id"]],
            step=run["step"],
            parameters={
                name: values[value["task_parameter"]]
                if isinstance(value, Mapping) else value
                for name, value in run.get("parameters", {}).items()
            },
            input_selections=_declared_input_selections(
                run["step"],
                run.get("inputs", {}),
                named_run_ids,
                f"task[{task.name}].runs[{run['id']}]",
            ),
        )
        for run in runs
    ]


def _validated_goal_requests(
    runnables: Sequence[Runnable],
    config: dict,
    registered_steps: dict[str, Step] | None,
    registered_tasks: Mapping[str, Task] | None,
    config_schema_paths: Mapping[str, Path] | None,
) -> tuple[dict[str, Step], list[_GoalRequest]]:
    """Resolve CLI or YAML selections into ordered concrete goal requests."""
    if registered_steps is None:
        from ASOkai._pipeline.catalog import get_pipeline_catalog

        catalog = get_pipeline_catalog()
        registered_steps = catalog.steps
        registered_tasks = catalog.tasks
        config_schema_paths = catalog.config_schema_paths

    cfg.validate_config_schema(
        config,
        plugin_schema_paths=config_schema_paths,
    )
    cfg.validate_configured_step_names(config, registered_steps)

    goal_requests: list[_GoalRequest] = []
    if "runs" in config:
        if runnables:
            raise ValueError(
                "Select runs in the configuration or with --step/--task/--workflow, "
                "not both."
            )
        named_run_ids: dict[str, str] = {}
        for index, declaration in enumerate(config["runs"]):
            if "id" not in declaration:
                continue
            name = declaration["id"]
            if name in named_run_ids:
                raise ValueError(f"$.runs[{index}].id: duplicate run id '{name}'.")
            named_run_ids[name] = f"runs.{name}"

        for index, declaration in enumerate(config["runs"]):
            if "step" in declaration:
                step_name = declaration["step"]
                step = registered_steps.get(step_name)
                if step is None:
                    raise ValueError(
                        f"$.runs[{index}].step: unknown step '{step_name}'."
                    )
                goal_requests.append(
                    _GoalRequest(
                        request_id=named_run_ids.get(
                            declaration.get("id"), f"runs.{index + 1}"
                        ),
                        step=step,
                        parameters=dict(declaration.get("parameters", {})),
                        input_selections=_declared_input_selections(
                            step,
                            declaration.get("inputs", {}),
                            named_run_ids,
                            f"$.runs[{index}]",
                        ),
                    )
                )
                continue

            task_name = declaration["task"]
            if registered_tasks is None:
                from ASOkai._pipeline.catalog import get_pipeline_catalog

                registered_tasks = get_pipeline_catalog().tasks
            task = registered_tasks.get(task_name)
            if task is None:
                raise ValueError(f"$.runs[{index}].task: unknown task '{task_name}'.")
            goal_requests.extend(
                _task_goal_requests(
                    task,
                    f"runs.{index + 1}",
                    config,
                    declaration.get("parameters", {}),
                    location=f"$.runs[{index}]",
                )
            )
        return registered_steps, goal_requests

    seen_goal_ids: set[str] = set()
    for runnable in runnables:
        for member in flatten_workflow_members(runnable):
            if isinstance(member, Task):
                requests = _task_goal_requests(member, None, config)
            else:
                requests = [_GoalRequest(member.name, member)]
            for request in requests:
                if request.request_id in seen_goal_ids:
                    continue
                seen_goal_ids.add(request.request_id)
                goal_requests.append(request)
    return registered_steps, goal_requests


def build_plan(
    runnables: Sequence[Runnable],
    config: dict,
    *,
    non_recursive: bool = False,
    force: bool = False,
    _registry: dict[str, Step] | None = None,
    _tasks: Mapping[str, Task] | None = None,
    _config_schema_paths: Mapping[str, Path] | None = None,
) -> ExecutionPlan:
    """Resolve requested runnables into a dependency-complete execution plan."""
    _registry, goal_requests = _validated_goal_requests(
        runnables,
        config,
        _registry,
        _tasks,
        _config_schema_paths,
    )

    builder = _PlanBuilder(
        config,
        _registry,
        non_recursive=non_recursive,
        force=force,
        output_validation_mode=cfg.output_validation_mode(config),
    )
    return builder.build(goal_requests)


def build_export_plan(
    runnables: Sequence[Runnable],
    config: dict,
    *,
    recursive: bool = False,
    _registry: dict[str, Step] | None = None,
    _tasks: Mapping[str, Task] | None = None,
    _config_schema_paths: Mapping[str, Path] | None = None,
) -> ExecutionPlan:
    """Resolve a file-system-independent plan for a CWL export bundle."""
    _registry, goal_requests = _validated_goal_requests(
        runnables,
        config,
        _registry,
        _tasks,
        _config_schema_paths,
    )
    builder = _PlanBuilder(
        config,
        _registry,
        non_recursive=False,
        force=True,
        validate_input_files=False,
    )
    return builder.build_export(goal_requests, recursive=recursive)
