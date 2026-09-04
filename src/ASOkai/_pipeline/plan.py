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
from ASOkai._pipeline.base import Runnable, expand_runnable_steps
from ASOkai._pipeline.contracts.execution import (
    ExecutionPlan,
    StepInputBinding,
    StepRun,
    StepRunOutput,
)
from ASOkai._pipeline.contracts.files import FileInput
from ASOkai._pipeline.output_receipts import reusable_output_paths
from ASOkai._pipeline.steps.base import Step

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _RequestedInputSource:
    """The path override or producer request found for one file input."""

    file_input: FileInput
    source: Path | _RunRequest


@dataclass
class _RunRequest:
    """One run requested during breadth-first dependency discovery."""

    request_id: str
    step: Step
    config: dict[str, Any]
    dependency_path: tuple[str, ...]
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
) -> bool:
    """Return whether an existing request describes this step configuration."""
    return type(request.step) is type(step) and request.config == config


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
            request.step.resolved_parameter_values(request.config).items()
        ),
        input_sources=tuple(
            (binding.file_input.name, binding.source) for binding in input_bindings
        ),
    )


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
    ) -> _RunRequest:
        """Reserve one request in the breadth-first discovery queue."""
        step.validate_output_declaration()
        existing_request = self.requests.get(request_id)
        if existing_request is not None:
            if not _request_matches_step_config(
                existing_request,
                step,
                config,
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
        path_override = file_input.configured_path_override(
            consumer_request.config,
            consumer_request.step.name,
        )
        if path_override is not None:
            return _RequestedInputSource(
                file_input=file_input,
                source=path_override,
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
        cfg.validate_step_config(
            run.config,
            [run.step],
            validate_input_files=self.validate_input_files,
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
                        )
                    )
                    continue
                producer_run = run_by_request_id[source.request_id]
                input_bindings.append(
                    StepInputBinding(
                        input_source.file_input,
                        producer_run.output(input_source.file_input.source),
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

    def build(self, goal_steps: list[Step]) -> ExecutionPlan:
        """Resolve reserved main goals into a dependency-complete plan."""
        goals, producer_first_runs = self._resolve_goals(goal_steps)
        runs_to_execute, reusable_outputs = self._schedule_required_runs(
            goals,
            producer_first_runs,
        )

        return ExecutionPlan(
            goals=goals,
            runs_to_execute=runs_to_execute,
            resolved_outputs=reusable_outputs,
        )

    def _resolve_goals(
        self,
        goal_steps: list[Step],
    ) -> tuple[tuple[StepRun, ...], tuple[StepRun, ...]]:
        """Discover dependencies and return goals plus producer-first runs."""
        for step in goal_steps:
            self._reserve_request(
                step.name,
                step,
                self.main_config,
                dependency_path=(step.name,),
            )
        self._discover_run_requests()

        run_by_request_id, producer_first_runs = self._resolve_run_requests()
        goals = tuple(run_by_request_id[step.name] for step in goal_steps)
        return goals, producer_first_runs

    def build_export(
        self,
        goal_steps: list[Step],
        *,
        recursive: bool,
    ) -> ExecutionPlan:
        """Resolve runs for export without consulting existing output files."""
        goals, producer_first_runs = self._resolve_goals(goal_steps)
        for run in producer_first_runs:
            self._validate_run(run)

        goal_runs = set(goals)
        included_runs = (
            producer_first_runs
            if recursive
            else tuple(run for run in producer_first_runs if run in goal_runs)
        )
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


def _validated_goal_steps(
    runnables: Sequence[Runnable],
    config: dict,
    registered_steps: dict[str, Step] | None,
    config_schema_paths: Mapping[str, Path] | None,
) -> tuple[dict[str, Step], list[Step]]:
    """Resolve the registry and validate shared planning inputs once."""
    if registered_steps is None:
        from ASOkai._pipeline.catalog import get_pipeline_catalog

        catalog = get_pipeline_catalog()
        registered_steps = catalog.steps
        config_schema_paths = catalog.config_schema_paths

    cfg.validate_config_schema(
        config,
        plugin_schema_paths=config_schema_paths,
    )
    cfg.validate_configured_step_names(config, registered_steps)

    goal_steps: list[Step] = []
    seen_goal_names: set[str] = set()
    for runnable in runnables:
        for step in expand_runnable_steps(runnable):
            if step.name in seen_goal_names:
                continue
            seen_goal_names.add(step.name)
            goal_steps.append(step)
    return registered_steps, goal_steps


def build_plan(
    runnables: Sequence[Runnable],
    config: dict,
    *,
    non_recursive: bool = False,
    force: bool = False,
    _registry: dict[str, Step] | None = None,
    _config_schema_paths: Mapping[str, Path] | None = None,
) -> ExecutionPlan:
    """Resolve requested runnables into a dependency-complete execution plan."""
    _registry, goal_steps = _validated_goal_steps(
        runnables,
        config,
        _registry,
        _config_schema_paths,
    )

    builder = _PlanBuilder(
        config,
        _registry,
        non_recursive=non_recursive,
        force=force,
        output_validation_mode=cfg.output_validation_mode(config),
    )
    return builder.build(goal_steps)


def build_export_plan(
    runnables: Sequence[Runnable],
    config: dict,
    *,
    recursive: bool = False,
    _registry: dict[str, Step] | None = None,
    _config_schema_paths: Mapping[str, Path] | None = None,
) -> ExecutionPlan:
    """Resolve a file-system-independent plan for a CWL export bundle."""
    _registry, goal_steps = _validated_goal_steps(
        runnables,
        config,
        _registry,
        _config_schema_paths,
    )
    builder = _PlanBuilder(
        config,
        _registry,
        non_recursive=False,
        force=True,
        validate_input_files=False,
    )
    return builder.build_export(goal_steps, recursive=recursive)
