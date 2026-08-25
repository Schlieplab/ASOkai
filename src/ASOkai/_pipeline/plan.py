#!/usr/bin/env python
"""
Filename: src/ASOkai/_pipeline/plan.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Version: 0.1.1
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

from ASOkai._types import Scalar
from ASOkai._pipeline import config as cfg
from ASOkai._pipeline.base import Runnable
from ASOkai._pipeline.contracts.execution import (
    ExecutionPlan,
    StepInputBinding,
    StepRun,
    StepRunOutput,
)
from ASOkai._pipeline.contracts.files import FileInput
from ASOkai._pipeline.steps.base import Step
from ASOkai._pipeline.tasks.base import Task
from ASOkai._pipeline.workflows.base import Workflow

logger = logging.getLogger(__name__)


def _flatten_goals(
    runnable: Runnable,
    seen_workflows: frozenset[str] = frozenset(),
) -> list[Step]:
    """Expand one runnable into the endpoint steps it requests."""
    if isinstance(runnable, Workflow):
        if runnable.name in seen_workflows:
            raise ValueError(f"Workflow '{runnable.name}' participates in a cycle.")
        seen = seen_workflows | {runnable.name}
        goals: list[Step] = []
        for member in runnable.members:
            goals.extend(_flatten_goals(member, seen))
        return goals
    if isinstance(runnable, Task):
        return list(runnable.steps)
    if isinstance(runnable, Step):
        return [runnable]
    raise TypeError(f"Unsupported runnable type: {type(runnable).__name__!r}.")


@dataclass(frozen=True)
class _RequestedInputSource:
    """The path override or producer request found for one file input."""

    file_input: FileInput
    path_override: Path | None = None
    producer_request_id: str | None = None


@dataclass
class _RunRequest:
    """One run requested during breadth-first dependency discovery."""

    request_id: str
    step: Step
    config: dict[str, Any]
    dependency_path: tuple[str, ...]
    input_sources: list[_RequestedInputSource] = field(default_factory=list)
    reusable_outputs: dict[str, Path] | None = None


@dataclass(frozen=True)
class _RunSignature:
    """Resolved values that determine whether requests can share one run."""

    step_name: str
    parameter_values: tuple[tuple[str, Scalar], ...]
    input_sources: tuple[tuple[str, Path | StepRunOutput], ...]


def _configured_producer_request_id(
    consumer_request_id: str,
    producer_step_name: str,
) -> str:
    """Return the contextual ID for a parameter-configured producer request."""
    return f"{consumer_request_id}.{producer_step_name}"


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
        goal_request_ids: set[str],
        non_recursive: bool,
        force: bool,
    ) -> None:
        self.main_config = main_config
        self.registered_steps = registered_steps
        self.goal_request_ids = goal_request_ids
        self.non_recursive = non_recursive
        self.force_goal_runs = force
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

    def _reusable_outputs(self, request: _RunRequest) -> dict[str, Path] | None:
        """Return valid existing outputs, or ``None`` when the request must run."""
        try:
            paths = request.step.validate_output_files(request.config)
        except (OSError, UnicodeError, TypeError, ValueError):
            return None
        logger.debug(
            "[plan] '%s' outputs are valid — reused.",
            request.request_id,
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
    ) -> None:
        """Reserve one request in the breadth-first discovery queue."""
        existing_request = self.requests.get(request_id)
        if existing_request is not None:
            if (
                type(existing_request.step) is not type(step)
                or existing_request.config != config
            ):
                raise ValueError(
                    f"Request id '{request_id}' resolves to conflicting step "
                    "configurations."
                )
            return

        request = _RunRequest(
            request_id=request_id,
            step=step,
            config=config,
            dependency_path=dependency_path,
        )
        self.requests[request_id] = request
        self.pending_request_ids.append(request_id)

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
                path_override=path_override,
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
            producer_dependency_path = (
                *consumer_request.dependency_path,
                producer.name,
            )

        self._reserve_request(
            producer_request_id,
            producer,
            producer_config,
            dependency_path=producer_dependency_path,
        )
        return _RequestedInputSource(
            file_input=file_input,
            producer_request_id=producer_request_id,
        )

    def _discover_dependencies(self) -> None:
        """Resolve queued requests and add missing producers breadth-first."""
        while self.pending_request_ids:
            request = self.requests[self.pending_request_ids.popleft()]
            cfg.validate_step_config(request.config, [request.step])

            goal_is_forced = (
                self.force_goal_runs and request.request_id in self.goal_request_ids
            )
            if not goal_is_forced:
                request.reusable_outputs = self._reusable_outputs(request)
            if request.reusable_outputs is not None:
                continue
            if self.non_recursive and request.request_id not in self.goal_request_ids:
                raise RuntimeError(
                    f"Run '{request.request_id}' is required, but its outputs are "
                    "missing or invalid. Omit --non-recursive to run missing "
                    "dependencies automatically."
                )

            request.input_sources.extend(
                self._discover_input_source(request, file_input)
                for file_input in request.step.spec.inputs
            )

    def _resolve_run_requests(
        self,
    ) -> tuple[
        dict[str, StepRun],
        tuple[StepRun, ...],
        dict[StepRunOutput, Path],
    ]:
        """Resolve requests producer-first into shared concrete runs."""
        pending_producer_ids: dict[str, set[str]] = {
            request_id: {
                input_source.producer_request_id
                for input_source in request.input_sources
                if input_source.producer_request_id is not None
            }
            for request_id, request in self.requests.items()
        }
        consumer_ids_by_producer_id: dict[str, list[str]] = {
            request_id: [] for request_id in self.requests
        }
        for consumer_request_id in self.requests:
            for producer_request_id in pending_producer_ids[consumer_request_id]:
                consumer_ids_by_producer_id[producer_request_id].append(
                    consumer_request_id
                )

        ready_request_ids = deque(
            request_id
            for request_id in self.requests
            if not pending_producer_ids[request_id]
        )
        run_by_request_id: dict[str, StepRun] = {}
        run_by_signature: dict[_RunSignature, StepRun] = {}
        runs_to_execute: list[StepRun] = []
        reusable_outputs: dict[StepRunOutput, Path] = {}

        while ready_request_ids:
            request_id = ready_request_ids.popleft()
            request = self.requests[request_id]
            input_bindings: list[StepInputBinding] = []
            for input_source in request.input_sources:
                if input_source.path_override is not None:
                    input_bindings.append(
                        StepInputBinding(
                            input_source.file_input,
                            input_source.path_override,
                        )
                    )
                    continue
                producer_request_id = input_source.producer_request_id
                assert producer_request_id is not None
                producer_run = run_by_request_id[producer_request_id]
                input_bindings.append(
                    StepInputBinding(
                        input_source.file_input,
                        producer_run.output(input_source.file_input.source),
                    )
                )

            if request.reusable_outputs is None:
                run_signature = _run_signature(request, input_bindings)
                run = run_by_signature.get(run_signature)
                if run is None:
                    run = StepRun(
                        run_id=request_id,
                        step=request.step,
                        config=request.config,
                        inputs=tuple(input_bindings),
                    )
                    run_by_signature[run_signature] = run
                    runs_to_execute.append(run)
            else:
                run = StepRun(
                    run_id=request_id,
                    step=request.step,
                    config=request.config,
                    inputs=tuple(input_bindings),
                )
                for output in run.step.spec.outputs:
                    reusable_outputs[run.output(output)] = request.reusable_outputs[
                        output.name
                    ]
            run_by_request_id[request_id] = run

            for consumer_request_id in consumer_ids_by_producer_id[request_id]:
                pending_producer_ids[consumer_request_id].discard(request_id)
                if not pending_producer_ids[consumer_request_id]:
                    ready_request_ids.append(consumer_request_id)

        if len(run_by_request_id) != len(self.requests):
            cycle = ", ".join(
                request_id
                for request_id in self.requests
                if pending_producer_ids[request_id]
            )
            raise ValueError(f"Dependency cycle detected involving run(s): {cycle}.")
        return run_by_request_id, tuple(runs_to_execute), reusable_outputs

    def build(self, goal_steps: list[Step]) -> ExecutionPlan:
        """Resolve reserved main goals into a dependency-complete plan."""
        for step in goal_steps:
            self._reserve_request(
                step.name,
                step,
                self.main_config,
                dependency_path=(step.name,),
            )
        self._discover_dependencies()

        run_by_request_id, runs_to_execute, reusable_outputs = (
            self._resolve_run_requests()
        )

        return ExecutionPlan(
            goals=tuple(run_by_request_id[step.name] for step in goal_steps),
            runs_to_execute=runs_to_execute,
            resolved_outputs=reusable_outputs,
        )


def build_plan(
    runnables: Sequence[Runnable],
    config: dict,
    *,
    non_recursive: bool = False,
    force: bool = False,
    _registry: dict[str, Step] | None = None,
) -> ExecutionPlan:
    """Resolve requested runnables into a dependency-complete execution plan."""
    if _registry is None:
        from ASOkai.Plugins._registry import get_steps

        _registry = get_steps()

    cfg.validate_config_schema(config)

    goal_steps: list[Step] = []
    seen_goal_names: set[str] = set()
    for runnable in runnables:
        for step in _flatten_goals(runnable):
            if step.name in seen_goal_names:
                continue
            seen_goal_names.add(step.name)
            goal_steps.append(step)

    builder = _PlanBuilder(
        config,
        _registry,
        goal_request_ids=seen_goal_names,
        non_recursive=non_recursive,
        force=force,
    )
    return builder.build(goal_steps)
