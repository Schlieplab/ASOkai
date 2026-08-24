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
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from ASOkai._pipeline import config as cfg
from ASOkai._pipeline.base import Runnable
from ASOkai._pipeline.contracts.files import FileInput, FileOutput
from ASOkai._pipeline.steps.base import Step
from ASOkai._pipeline.tasks.base import Task
from ASOkai._pipeline.workflows.base import Workflow


logger = logging.getLogger(__name__)


@dataclass(frozen=True, eq=False)
class StepRun:
    """One concrete execution of a step under resolved configuration."""

    run_id: str
    name: str
    step: Step
    config: Mapping[str, Any] = field(repr=False)
    inputs: tuple[StepInputBinding, ...] = ()

    def __post_init__(self) -> None:
        if type(self.run_id) is not str or not self.run_id.strip():
            raise ValueError("StepRun.run_id must be a non-blank string.")
        if type(self.name) is not str or not self.name.strip():
            raise ValueError("StepRun.name must be a non-blank string.")
        if not isinstance(self.step, Step):
            raise TypeError("StepRun.step must be a Step.")
        if not isinstance(self.config, Mapping):
            raise TypeError("StepRun.config must be a mapping.")

        inputs = tuple(self.inputs)
        if any(not isinstance(item, StepInputBinding) for item in inputs):
            raise TypeError(
                "StepRun.inputs must contain only StepInputBinding values."
            )
        input_names = [item.file_input.name for item in inputs]
        duplicates = sorted(
            {name for name in input_names if input_names.count(name) > 1}
        )
        if duplicates:
            raise ValueError(
                "StepRun input bindings contain duplicate name(s): "
                f"{', '.join(duplicates)}."
            )

        object.__setattr__(
            self,
            "config",
            MappingProxyType(deepcopy(dict(self.config))),
        )
        object.__setattr__(self, "inputs", inputs)

    def __eq__(self, other: object) -> bool:
        """Concrete runs compare by their stable resolved identity."""
        return isinstance(other, StepRun) and self.run_id == other.run_id

    def __hash__(self) -> int:
        return hash(self.run_id)

    def output(self, output: FileOutput) -> StepRunOutput:
        """Return one output port qualified by this concrete run."""
        try:
            declared = self.step.spec.output(output.name)
        except KeyError as error:
            raise ValueError(
                f"Output '{output.name}' does not belong to step "
                f"'{self.step.name}'."
            ) from error
        if declared is not output:
            raise ValueError(
                f"Output '{output.name}' does not belong to step "
                f"'{self.step.name}'."
            )
        return StepRunOutput(self, output)


@dataclass(frozen=True)
class StepRunOutput:
    """One declared file output produced by one concrete step run."""

    run: StepRun
    output: FileOutput

    def __post_init__(self) -> None:
        if not isinstance(self.run, StepRun):
            raise TypeError("StepRunOutput.run must be a StepRun.")
        if not isinstance(self.output, FileOutput):
            raise TypeError("StepRunOutput.output must be a FileOutput.")


@dataclass(frozen=True)
class StepInputBinding:
    """A step input resolved to an external path or producer-run output."""

    file_input: FileInput
    source: Path | StepRunOutput

    def __post_init__(self) -> None:
        if not isinstance(self.file_input, FileInput):
            raise TypeError("StepInputBinding.file_input must be a FileInput.")
        if isinstance(self.source, Path):
            object.__setattr__(self, "source", self.source.resolve())
        elif not isinstance(self.source, StepRunOutput):
            raise TypeError(
                "StepInputBinding.source must be a Path or StepRunOutput."
            )


@dataclass(frozen=True)
class ExecutionPlan:
    """Resolved goals, scheduled runs, and reusable run outputs."""

    goals: tuple[StepRun, ...]
    runs_to_execute: tuple[StepRun, ...]
    resolved_outputs: Mapping[StepRunOutput, Path] = field(default_factory=dict)

    def __post_init__(self) -> None:
        goals = tuple(self.goals)
        runs_to_execute = tuple(self.runs_to_execute)
        if any(not isinstance(run, StepRun) for run in goals):
            raise TypeError("ExecutionPlan.goals must contain only StepRun values.")
        if any(not isinstance(run, StepRun) for run in runs_to_execute):
            raise TypeError(
                "ExecutionPlan.runs_to_execute must contain only StepRun values."
            )

        resolved_outputs: dict[StepRunOutput, Path] = {}
        for output, path in self.resolved_outputs.items():
            if not isinstance(output, StepRunOutput):
                raise TypeError(
                    "ExecutionPlan.resolved_outputs keys must be StepRunOutput values."
                )
            if not isinstance(path, Path):
                raise TypeError(
                    "ExecutionPlan.resolved_outputs values must be Path values."
                )
            resolved_outputs[output] = path.resolve()

        object.__setattr__(self, "goals", goals)
        object.__setattr__(self, "runs_to_execute", runs_to_execute)
        object.__setattr__(
            self,
            "resolved_outputs",
            MappingProxyType(resolved_outputs),
        )


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


class _GoalResolver:
    """Resolve requested main runs and their required producer runs."""

    def __init__(
        self,
        config: dict,
        registry: Mapping[str, Step],
        *,
        goal_names: set[str],
        non_recursive: bool,
        force: bool,
    ) -> None:
        self.config = config
        self.registry = registry
        self.goal_names = goal_names
        self.non_recursive = non_recursive
        self.forced_run_ids = goal_names if force else set()
        self.runs: dict[str, StepRun] = {}
        self.resolving: set[str] = set()
        self.runs_to_execute: list[StepRun] = []
        self.resolved_outputs: dict[StepRunOutput, Path] = {}

    def _producer(
        self,
        consumer: Step,
        file_input: FileInput,
    ) -> Step:
        """Return and validate the registered producer for one file input."""
        source = file_input.source
        producer = self.registry.get(source.producer)
        if producer is None:
            raise ValueError(
                f"Step '{consumer.name}' references unknown producer "
                f"'{source.producer}'."
            )
        try:
            declared = producer.spec.output(source.name)
        except KeyError as error:
            raise ValueError(
                f"Step '{consumer.name}' input '{file_input.name}' references "
                f"unknown output '{source.name}' on step '{source.producer}'."
            ) from error
        if declared is not source:
            raise ValueError(
                f"Step '{consumer.name}' input '{file_input.name}' references "
                f"an output declaration that does not belong to "
                f"'{source.producer}'."
            )
        return producer

    def _existing_outputs(self, run: StepRun) -> bool:
        """Record valid existing outputs and report whether the run is done."""
        try:
            paths = run.step.validate_output_files(dict(run.config))
        except (OSError, UnicodeError, TypeError, ValueError):
            return False
        for output in run.step.spec.outputs:
            self.resolved_outputs[run.output(output)] = paths[output.name]
        logger.debug("[plan] '%s' outputs are valid — reused.", run.name)
        return True

    def _resolve_input(self, step: Step, file_input: FileInput) -> StepInputBinding:
        """Resolve one external input path or its producer's main run."""
        path_override = file_input.configured_path_override(
            self.config,
            step.name,
        )
        if path_override is not None:
            return StepInputBinding(file_input, path_override)

        producer = self._producer(step, file_input)
        may_schedule = not self.non_recursive or producer.name in self.goal_names
        producer_run = self.resolve(producer, may_schedule=may_schedule)
        return StepInputBinding(
            file_input,
            producer_run.output(file_input.source),
        )

    def resolve(self, step: Step, *, may_schedule: bool = True) -> StepRun:
        """Resolve one main run, recursively resolving inputs when required."""
        run_id = step.name
        existing = self.runs.get(run_id)
        if existing is not None:
            return existing
        if run_id in self.resolving:
            raise ValueError(
                f"Dependency cycle detected involving step '{step.name}'."
            )

        self.resolving.add(run_id)
        try:
            cfg.validate_step_config(self.config, [step])
            for file_input in step.spec.inputs:
                if file_input.configured_parameters(
                    self.config,
                    step.name,
                ) is not None:
                    raise RuntimeError(
                        f"Input '{step.name}.{file_input.name}' configures a "
                        "separate producer run. Resolving additional configured "
                        "runs is the next implementation step."
                    )
            run = StepRun(
                run_id=run_id,
                name=step.name,
                step=step,
                config=self.config,
            )
            forced = run_id in self.forced_run_ids
            if not forced and self._existing_outputs(run):
                self.runs[run_id] = run
                return run
            if not may_schedule:
                raise RuntimeError(
                    f"Step '{step.name}' is required, but its outputs are "
                    "missing or invalid. Omit --non-recursive to run missing "
                    "dependencies automatically."
                )

            inputs = tuple(
                self._resolve_input(step, file_input)
                for file_input in step.spec.inputs
            )
            run = StepRun(
                run_id=run_id,
                name=step.name,
                step=step,
                config=self.config,
                inputs=inputs,
            )
            self.runs[run_id] = run
            self.runs_to_execute.append(run)
            return run
        finally:
            self.resolving.discard(run_id)


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
    seen_names: set[str] = set()
    for runnable in runnables:
        for step in _flatten_goals(runnable):
            if step.name in seen_names:
                continue
            seen_names.add(step.name)
            goal_steps.append(step)

    resolver = _GoalResolver(
        config,
        _registry,
        goal_names=seen_names,
        non_recursive=non_recursive,
        force=force,
    )
    goals = tuple(resolver.resolve(step) for step in goal_steps)
    return ExecutionPlan(
        goals=goals,
        runs_to_execute=tuple(resolver.runs_to_execute),
        resolved_outputs=resolver.resolved_outputs,
    )
