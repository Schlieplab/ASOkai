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
from typing import Any, Mapping

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
class _PendingInputBinding:
    """An input binding waiting for its producer StepRun to be constructed."""

    file_input: FileInput
    producer_run_id: str


@dataclass
class _RunDraft:
    """Mutable run state used only while constructing an execution plan."""

    run_id: str
    step: Step
    config: dict[str, Any]
    step_lineage: tuple[str, ...]
    inputs: list[StepInputBinding | _PendingInputBinding] = field(
        default_factory=list,
    )
    reusable_outputs: dict[str, Path] | None = None


def _configured_producer_run_id(
    consumer_run_id: str,
    producer_step_name: str,
) -> str:
    """Return the contextual ID for a parameter-configured producer run."""
    return f"{consumer_run_id}.{producer_step_name}"


class _PlanBuilder:
    """Discover concrete runs breadth-first, then order them for execution."""

    def __init__(
        self,
        main_config: dict,
        registered_steps: Mapping[str, Step],
        *,
        main_goal_ids: set[str],
        non_recursive: bool,
        force: bool,
    ) -> None:
        self.main_config = main_config
        self.registered_steps = registered_steps
        self.main_goal_ids = main_goal_ids
        self.non_recursive = non_recursive
        self.force_goals = force
        self.run_drafts: dict[str, _RunDraft] = {}
        self.pending_run_ids: deque[str] = deque()

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

    def _reusable_outputs(self, run_draft: _RunDraft) -> dict[str, Path] | None:
        """Return valid existing outputs, or ``None`` when the run must execute."""
        try:
            paths = run_draft.step.validate_output_files(run_draft.config)
        except (OSError, UnicodeError, TypeError, ValueError):
            return None
        logger.debug("[plan] '%s' outputs are valid — reused.", run_draft.run_id)
        return paths

    def _configured_producer_config(
        self,
        file_input: FileInput,
        parameter_values: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Return main configuration with one input's producer overrides."""
        overrides: dict[str, Any] = {}
        for name, value in parameter_values.items():
            parameter = file_input.configurable_parameter(name)
            assert parameter.config is not None
            overrides[parameter.config] = value
        return cfg.apply_overrides(deepcopy(self.main_config), overrides)

    def _reserve_run(
        self,
        run_id: str,
        step: Step,
        config: dict[str, Any],
        *,
        step_lineage: tuple[str, ...],
    ) -> None:
        """Reserve one named run in the breadth-first discovery queue."""
        reserved_run = self.run_drafts.get(run_id)
        if reserved_run is not None:
            if (
                type(reserved_run.step) is not type(step)
                or reserved_run.config != config
            ):
                raise ValueError(
                    f"Run id '{run_id}' resolves to conflicting step "
                    "configurations."
                )
            return

        run_draft = _RunDraft(
            run_id=run_id,
            step=step,
            config=config,
            step_lineage=step_lineage,
        )
        self.run_drafts[run_id] = run_draft
        self.pending_run_ids.append(run_id)

    def _discover_input(
        self,
        consumer_run: _RunDraft,
        file_input: FileInput,
    ) -> StepInputBinding | _PendingInputBinding:
        """Resolve one override or discover its concrete producer run."""
        path_override = file_input.configured_path_override(
            consumer_run.config,
            consumer_run.step.name,
        )
        if path_override is not None:
            return StepInputBinding(file_input, path_override)

        producer = self._registered_producer(consumer_run.step, file_input)
        if producer.name in consumer_run.step_lineage:
            cycle = " -> ".join(
                (*consumer_run.step_lineage, producer.name)
            )
            raise ValueError(f"Dependency cycle detected: {cycle}.")

        parameter_values = file_input.configured_parameters(
            consumer_run.config,
            consumer_run.step.name,
        )
        if parameter_values is None:
            producer_run_id = producer.name
            producer_config = self.main_config
            producer_step_lineage = (producer.name,)
        else:
            producer_run_id = _configured_producer_run_id(
                consumer_run.run_id,
                producer.name,
            )
            producer_config = self._configured_producer_config(
                file_input,
                parameter_values,
            )
            producer_step_lineage = (
                *consumer_run.step_lineage,
                producer.name,
            )

        self._reserve_run(
            producer_run_id,
            producer,
            producer_config,
            step_lineage=producer_step_lineage,
        )
        return _PendingInputBinding(file_input, producer_run_id)

    def _discover_dependencies(self) -> None:
        """Resolve queued runs and add their missing producers breadth-first."""
        while self.pending_run_ids:
            run_draft = self.run_drafts[self.pending_run_ids.popleft()]
            cfg.validate_step_config(run_draft.config, [run_draft.step])

            goal_is_forced = (
                self.force_goals
                and run_draft.run_id in self.main_goal_ids
            )
            if not goal_is_forced:
                run_draft.reusable_outputs = self._reusable_outputs(run_draft)
            if run_draft.reusable_outputs is not None:
                continue
            if (
                self.non_recursive
                and run_draft.run_id not in self.main_goal_ids
            ):
                raise RuntimeError(
                    f"Run '{run_draft.run_id}' is required, but its outputs are "
                    "missing or invalid. Omit --non-recursive to run missing "
                    "dependencies automatically."
                )

            run_draft.inputs.extend(
                self._discover_input(run_draft, file_input)
                for file_input in run_draft.step.spec.inputs
            )

    def _dependency_ordered_run_ids(self) -> list[str]:
        """Return discovered run IDs with every producer before its consumers."""
        dependencies: dict[str, set[str]] = {
            run_id: {
                binding.producer_run_id
                for binding in draft.inputs
                if isinstance(binding, _PendingInputBinding)
            }
            for run_id, draft in self.run_drafts.items()
        }
        consumers: dict[str, list[str]] = {
            run_id: [] for run_id in self.run_drafts
        }
        for consumer_run_id in self.run_drafts:
            for producer_run_id in dependencies[consumer_run_id]:
                consumers[producer_run_id].append(consumer_run_id)

        ready = deque(
            run_id
            for run_id in self.run_drafts
            if not dependencies[run_id]
        )
        ordered: list[str] = []
        while ready:
            producer_run_id = ready.popleft()
            ordered.append(producer_run_id)
            for consumer_run_id in consumers[producer_run_id]:
                dependencies[consumer_run_id].discard(producer_run_id)
                if not dependencies[consumer_run_id]:
                    ready.append(consumer_run_id)

        if len(ordered) != len(self.run_drafts):
            cycle = ", ".join(
                run_id
                for run_id in self.run_drafts
                if dependencies[run_id]
            )
            raise ValueError(
                f"Dependency cycle detected involving run(s): {cycle}."
            )
        return ordered

    def _materialize_runs(
        self,
        ordered_run_ids: list[str],
    ) -> tuple[dict[str, StepRun], dict[StepRunOutput, Path]]:
        """Construct immutable runs and qualify every reusable output."""
        runs: dict[str, StepRun] = {}
        reusable_outputs: dict[StepRunOutput, Path] = {}
        for run_id in ordered_run_ids:
            draft = self.run_drafts[run_id]
            inputs: list[StepInputBinding] = []
            for draft_input in draft.inputs:
                if isinstance(draft_input, StepInputBinding):
                    inputs.append(draft_input)
                    continue
                producer_run = runs[draft_input.producer_run_id]
                inputs.append(
                    StepInputBinding(
                        draft_input.file_input,
                        producer_run.output(draft_input.file_input.source),
                    )
                )
            run = StepRun(
                run_id=run_id,
                step=draft.step,
                config=draft.config,
                inputs=tuple(inputs),
            )
            runs[run_id] = run
            if draft.reusable_outputs is not None:
                for output in run.step.spec.outputs:
                    reusable_outputs[run.output(output)] = (
                        draft.reusable_outputs[output.name]
                    )
        return runs, reusable_outputs

    def build(self, goal_steps: list[Step]) -> ExecutionPlan:
        """Resolve reserved main goals into a dependency-complete plan."""
        for step in goal_steps:
            self._reserve_run(
                step.name,
                step,
                self.main_config,
                step_lineage=(step.name,),
            )
        self._discover_dependencies()

        ordered_run_ids = self._dependency_ordered_run_ids()
        runs, reusable_outputs = self._materialize_runs(ordered_run_ids)

        return ExecutionPlan(
            goals=tuple(runs[step.name] for step in goal_steps),
            runs_to_execute=tuple(
                runs[run_id]
                for run_id in ordered_run_ids
                if self.run_drafts[run_id].reusable_outputs is None
            ),
            resolved_outputs=reusable_outputs,
        )


def build_plan(
    runnables: list[Runnable],
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
        main_goal_ids=seen_goal_names,
        non_recursive=non_recursive,
        force=force,
    )
    return builder.build(goal_steps)
