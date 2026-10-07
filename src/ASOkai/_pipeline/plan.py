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
from ASOkai._pipeline.contracts.parameters import ScalarParam
from ASOkai._pipeline.contracts.run_spec import (
    RunInput,
    FromRun,
    RunSpec,
    parse_run_input,
)
from ASOkai._pipeline.output_receipts import reusable_output_paths
from ASOkai._pipeline.steps.base import Step
from ASOkai._pipeline.tasks.base import (
    Task,
    validate_task_parameter_contract,
    validate_task_outputs,
    validate_task_runs,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _ExplicitInput:
    """An input selection and its declaration location."""

    source: RunInput
    location: str


@dataclass(frozen=True)
class _RequestedInputSource:
    """The path or producer request found for one file input."""

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


def _run_signature(
    run: StepRun,
) -> _RunSignature:
    """Return the result-affecting signature of a resolved run."""
    return _RunSignature(
        step_name=run.step.name,
        parameter_values=tuple(run.parameters.items()),
        input_sources=tuple(
            (binding.file_input.name, binding.source) for binding in run.inputs
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
        named_outputs: Mapping[str, FromRun] | None = None,
    ) -> None:
        self.main_config = main_config
        self.registered_steps = registered_steps
        self.non_recursive = non_recursive
        self.force_goal_runs = force
        self.validate_input_files = validate_input_files
        self.output_validation_mode = output_validation_mode
        self.named_outputs = named_outputs or {}
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
        if explicit is None:
            configured = file_input.configured_source(
                consumer_request.config,
                consumer_request.step.name,
            )
            if configured is not None:
                if isinstance(configured, FromRun):
                    configured = self.named_outputs.get(
                        f"{configured.run_id}.{configured.output_name}",
                        configured,
                    )
                explicit = _ExplicitInput(
                    configured,
                    f"$.{file_input.configuration_path(consumer_request.step.name)}",
                )
        if explicit is not None:
            if isinstance(explicit.source, Path):
                return _RequestedInputSource(
                    file_input=file_input,
                    source=explicit.source,
                    selection_path=f"{explicit.location}.path",
                )
            producer_request = self.requests.get(explicit.source.run_id)
            if producer_request is None:
                raise ValueError(
                    f"{explicit.location}.from: unknown named run "
                    f"'{explicit.source.run_id}'."
                )
            try:
                output = producer_request.step.spec.output(explicit.source.output_name)
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

        if file_input.source is None:
            raise ValueError(
                f"Run '{consumer_request.request_id}' input '{file_input.name}' "
                "requires a path or a named producer run."
            )

        producer = self._registered_producer(consumer_request.step, file_input)
        if producer.name in consumer_request.dependency_path:
            cycle = " -> ".join((*consumer_request.dependency_path, producer.name))
            raise ValueError(f"Dependency cycle detected: {cycle}.")

        producer_request = self._reserve_request(
            producer.name,
            producer,
            self.main_config,
            dependency_path=(producer.name,),
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
            input_configurations=run.input_configurations(),
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

            candidate = StepRun(
                run_id=request.request_id,
                step=request.step,
                config=request.config,
                inputs=tuple(input_bindings),
                parameters=request.parameters,
            )
            run_signature = _run_signature(candidate)
            run = run_by_signature.get(run_signature)
            if run is None:
                run = candidate
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

    def build(self, run_specs: list[RunSpec]) -> ExecutionPlan:
        """Resolve reserved main goals into a dependency-complete plan."""
        goals, producer_first_runs = self._resolve_goals(run_specs)
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
        run_specs: list[RunSpec],
    ) -> tuple[tuple[StepRun, ...], tuple[StepRun, ...]]:
        """Discover dependencies and return goals plus producer-first runs."""
        available_ids = {spec.run_id for spec in run_specs}
        for spec in run_specs:
            input_selections: dict[str, _ExplicitInput] = {}
            declared_inputs = {item.name for item in spec.step.spec.inputs}
            location_prefix = spec.location or f"run[{spec.run_id}]"
            for name, source in spec.inputs.items():
                location = f"{location_prefix}.inputs.{name}"
                if name not in declared_inputs:
                    raise ValueError(
                        f"{location}: step '{spec.step.name}' has no input "
                        "with this name."
                    )
                if isinstance(source, Path):
                    input_selections[name] = _ExplicitInput(source, location)
                    continue
                if not isinstance(source, FromRun):
                    raise TypeError(
                        f"{location} must specify a path or from reference."
                    )
                producer_id = source.run_id
                if type(producer_id) is not str or producer_id not in available_ids:
                    raise ValueError(
                        f"{location}.from: unknown named run '{producer_id}'."
                    )
                input_selections[name] = _ExplicitInput(source, location)
            self._reserve_request(
                spec.run_id,
                spec.step,
                self.main_config,
                dependency_path=(spec.step.name,),
                parameters=spec.parameters,
                input_selections=input_selections,
            )
        self._discover_run_requests()

        run_by_request_id, producer_first_runs = self._resolve_run_requests()
        goals = tuple(run_by_request_id[spec.run_id] for spec in run_specs)
        return goals, producer_first_runs

    def build_export(
        self,
        run_specs: list[RunSpec],
        *,
        recursive: bool,
    ) -> ExecutionPlan:
        """Resolve runs for export without consulting existing output files."""
        goals, producer_first_runs = self._resolve_goals(run_specs)
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
                    external_outputs[source] = source.run.output_path(source.output)

        return ExecutionPlan(
            goals=goals,
            runs_to_execute=included_runs,
            resolved_outputs=external_outputs,
        )


def _normalized_inputs(
    step: Step,
    declarations: Mapping[str, Any],
    named_outputs: Mapping[str, FromRun],
    location_prefix: str,
) -> dict[str, RunInput]:
    """Qualify declared input links for one selected step run."""
    selections: dict[str, RunInput] = {}
    declared_inputs = {file_input.name for file_input in step.spec.inputs}
    for name, declaration in declarations.items():
        location = f"{location_prefix}.inputs.{name}"
        if name not in declared_inputs:
            raise ValueError(
                f"{location}: step '{step.name}' has no input with this name."
            )
        source = parse_run_input(declaration)
        if isinstance(source, Path):
            selections[name] = source
            continue
        resolved = named_outputs.get(f"{source.run_id}.{source.output_name}")
        if resolved is None:
            if any(key.startswith(f"{source.run_id}.") for key in named_outputs):
                raise ValueError(
                    f"{location}.from: run '{source.run_id}' has no output "
                    f"'{source.output_name}'."
                )
            raise ValueError(f"{location}.from: unknown named run '{source.run_id}'.")
        selections[name] = resolved
    return selections


def _task_parameters(
    runs: Sequence[RunSpec],
    overrides: Mapping[str, Any],
    location: str,
) -> dict[str, Any]:
    """Validate parameters for child ports left open by the task."""
    if not isinstance(overrides, Mapping):
        raise TypeError(f"{location}.parameters must be a mapping.")
    declarations: dict[str, list[ScalarParam]] = {}
    for run in runs:
        for parameter in run.step.spec.params:
            if parameter.name not in run.parameters:
                declarations.setdefault(parameter.name, []).append(parameter)
                path = parameter.selection_path
                if path != parameter.name:
                    declarations.setdefault(path, []).append(parameter)
    unknown = set(overrides) - declarations.keys()
    if unknown:
        names = ", ".join(sorted(str(name) for name in unknown))
        raise ValueError(f"{location}.parameters has unknown parameter(s): {names}.")
    for name, value in overrides.items():
        for parameter in declarations[name]:
            try:
                parameter.validate(value)
            except (TypeError, ValueError) as error:
                raise ValueError(f"{location}.parameters.{name}: {error}") from error
    return dict(overrides)


def _matching_task_parameters(
    step: Step,
    values: Mapping[str, Any],
    fixed: Mapping[str, Any],
    location: str,
) -> dict[str, Any]:
    """Apply task values to child parameters by exact path or legacy name."""
    matched: dict[str, Any] = {}
    for parameter in step.spec.params:
        if parameter.name in fixed:
            continue
        path = parameter.selection_path
        keys = (parameter.name,) if path == parameter.name else (parameter.name, path)
        supplied = [key for key in keys if key in values]
        if len(supplied) > 1:
            raise ValueError(
                f"{location}.parameters specifies '{parameter.name}' both "
                "by name and configuration path."
            )
        if supplied:
            matched[parameter.name] = values[supplied[0]]
    return matched


def _task_run_specs(
    task: Task,
    prefix: str | None,
    parameters: Mapping[str, Any] | None = None,
    run_overrides: Sequence[Mapping[str, Any]] = (),
    global_outputs: Mapping[str, FromRun] | None = None,
    *,
    location: str | None = None,
) -> list[RunSpec]:
    """Apply task-wide and child-specific overrides to declared runs."""
    selection_location = location or f"task[{task.name}]"
    validate_task_parameter_contract(task)
    runs = (
        validate_task_runs(task)
        if hasattr(task, "runs")
        else tuple(RunSpec(step.name, step) for step in task.steps)
    )
    values = _task_parameters(
        runs, parameters if parameters is not None else {}, selection_location
    )
    if not hasattr(task, "runs"):
        if run_overrides:
            raise ValueError(f"{selection_location}.runs requires named task runs.")
        return [
            RunSpec(
                f"{prefix}.{step.name}" if prefix else step.name,
                step,
                parameters=_matching_task_parameters(
                    step, values, {}, selection_location
                ),
            )
            for step in task.steps
        ]

    context = prefix or task.name
    named_run_ids = {run.run_id: f"{context}.{run.run_id}" for run in runs}
    overrides_by_id: dict[str, tuple[Mapping[str, Any], str]] = {}
    for index, override in enumerate(run_overrides):
        child_id = override["id"]
        child_location = f"{selection_location}.runs[{index}]"
        if child_id not in named_run_ids:
            raise ValueError(f"{child_location}.id: unknown task run '{child_id}'.")
        if child_id in overrides_by_id:
            raise ValueError(f"{child_location}.id: duplicate task run '{child_id}'.")
        overrides_by_id[child_id] = (override, child_location)

    local_outputs = {
        f"{run.run_id}.{output.name}": FromRun(
            named_run_ids[run.run_id], output.name
        )
        for run in runs
        for output in run.step.spec.outputs
    }
    available_outputs = {**(global_outputs or {}), **local_outputs}
    result: list[RunSpec] = []
    for run in runs:
        override, child_location = overrides_by_id.get(
            run.run_id, ({}, f"task[{task.name}].runs[{run.run_id}]")
        )
        child_parameters = override.get("parameters", {})
        declared_parameters = {
            parameter.name: parameter for parameter in run.step.spec.params
        }
        unknown_parameters = set(child_parameters) - declared_parameters.keys()
        if unknown_parameters:
            names = ", ".join(sorted(str(name) for name in unknown_parameters))
            raise ValueError(
                f"{child_location}.parameters has unknown parameter(s): {names}."
            )
        fixed_parameters = set(child_parameters) & run.parameters.keys()
        if fixed_parameters:
            names = ", ".join(sorted(fixed_parameters))
            raise ValueError(
                f"{child_location}.parameters cannot override task-declared "
                f"parameter(s): {names}."
            )
        for name, value in child_parameters.items():
            try:
                declared_parameters[name].validate(value)
            except (TypeError, ValueError) as error:
                raise ValueError(
                    f"{child_location}.parameters.{name}: {error}"
                ) from error
        matching_values = _matching_task_parameters(
            run.step, values, run.parameters, selection_location
        )
        inputs = _normalized_inputs(
            run.step,
            run.inputs,
            local_outputs,
            f"task[{task.name}].runs[{run.run_id}]",
        )
        fixed_inputs = set(override.get("inputs", {})) & run.inputs.keys()
        if fixed_inputs:
            names = ", ".join(sorted(fixed_inputs))
            raise ValueError(
                f"{child_location}.inputs cannot override task-declared "
                f"input(s): {names}."
            )
        inputs.update(
            _normalized_inputs(
                run.step,
                override.get("inputs", {}),
                available_outputs,
                child_location,
            )
        )
        result.append(
            RunSpec(
                run_id=named_run_ids[run.run_id],
                step=run.step,
                parameters={
                    **matching_values,
                    **child_parameters,
                    **run.parameters,
                },
                inputs=inputs,
                location=child_location,
            )
        )
    return result


def _validated_run_specs(
    runnables: Sequence[Runnable],
    config: dict,
    registered_steps: dict[str, Step] | None,
    registered_tasks: Mapping[str, Task] | None,
    config_schema_paths: Mapping[str, Path] | None,
) -> tuple[dict[str, Step], list[RunSpec], dict[str, FromRun]]:
    """Normalize CLI or YAML selections into ordered step run specs."""
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

    run_specs: list[RunSpec] = []
    if "runs" in config:
        if runnables:
            raise ValueError(
                "Select runs in the configuration or with --step/--task/--workflow, "
                "not both."
            )
        declarations = cfg.assign_run_ids(config["runs"])
        named_run_ids: dict[str, str] = {}
        named_outputs: dict[str, FromRun] = {}
        selection_ids: set[str] = set()
        for index, declaration in enumerate(declarations):
            name = declaration["id"]
            if name in selection_ids:
                raise ValueError(f"$.runs[{index}].id: duplicate run id '{name}'.")
            selection_ids.add(name)
            if "step" in declaration:
                named_run_ids[name] = f"runs.{name}"
                step = registered_steps.get(declaration["step"])
                if step is None:
                    raise ValueError(
                        f"$.runs[{index}].step: unknown step '{declaration['step']}'."
                    )
                for output in step.spec.outputs:
                    named_outputs[f"{name}.{output.name}"] = FromRun(
                        named_run_ids[name], output.name
                    )
                continue
            task_name = declaration["task"]
            if registered_tasks is None:
                from ASOkai._pipeline.catalog import get_pipeline_catalog

                registered_tasks = get_pipeline_catalog().tasks
            task = registered_tasks.get(task_name)
            if task is None:
                raise ValueError(f"$.runs[{index}].task: unknown task '{task_name}'.")
            if hasattr(task, "runs"):
                task_runs = validate_task_runs(task)
                for child in task_runs:
                    named_run_ids[f"{name}.{child.run_id}"] = (
                        f"runs.{name}.{child.run_id}"
                    )
                    for output in child.step.spec.outputs:
                        named_outputs[f"{name}.{child.run_id}.{output.name}"] = (
                            FromRun(
                                named_run_ids[f"{name}.{child.run_id}"],
                                output.name,
                            )
                        )
                for alias, reference in validate_task_outputs(
                    task, {child.run_id: child for child in task_runs}
                ).items():
                    named_outputs[f"{name}.{alias}"] = FromRun(
                        named_run_ids[f"{name}.{reference.run_id}"],
                        reference.output_name,
                    )

        for index, declaration in enumerate(declarations):
            if "step" in declaration:
                step_name = declaration["step"]
                step = registered_steps.get(step_name)
                if step is None:
                    raise ValueError(
                        f"$.runs[{index}].step: unknown step '{step_name}'."
                    )
                run_specs.append(
                    RunSpec(
                        run_id=named_run_ids[declaration["id"]],
                        step=step,
                        parameters=dict(declaration.get("parameters", {})),
                        inputs=_normalized_inputs(
                            step,
                            declaration.get("inputs", {}),
                            named_outputs,
                            f"$.runs[{index}]",
                        ),
                        location=f"$.runs[{index}]",
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
            run_specs.extend(
                _task_run_specs(
                    task,
                    f"runs.{declaration['id']}",
                    declaration.get("parameters", {}),
                    declaration.get("runs", ()),
                    named_outputs,
                    location=f"$.runs[{index}]",
                )
            )
        return registered_steps, run_specs, named_outputs

    named_outputs: dict[str, FromRun] = {}
    seen_goal_ids: set[str] = set()
    for runnable in runnables:
        for member in flatten_workflow_members(runnable):
            if isinstance(member, Task):
                requests = _task_run_specs(member, None)
                if hasattr(member, "runs"):
                    task_runs = validate_task_runs(member)
                    for alias, reference in validate_task_outputs(
                        member, {run.run_id: run for run in task_runs}
                    ).items():
                        named_outputs[f"{member.name}.{alias}"] = FromRun(
                            f"{member.name}.{reference.run_id}",
                            reference.output_name,
                        )
            else:
                requests = [RunSpec(member.name, member)]
            for request in requests:
                for output in request.step.spec.outputs:
                    named_outputs[f"{request.run_id}.{output.name}"] = FromRun(
                        request.run_id, output.name
                    )
                if request.run_id in seen_goal_ids:
                    continue
                seen_goal_ids.add(request.run_id)
                run_specs.append(request)
    return registered_steps, run_specs, named_outputs


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
    _registry, run_specs, named_outputs = _validated_run_specs(
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
        named_outputs=named_outputs,
    )
    return builder.build(run_specs)


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
    _registry, run_specs, named_outputs = _validated_run_specs(
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
        named_outputs=named_outputs,
    )
    return builder.build_export(run_specs, recursive=recursive)
