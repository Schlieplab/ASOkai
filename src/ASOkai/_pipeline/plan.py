#!/usr/bin/env python
"""
Filename: src/ASOkai/_pipeline/plan.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Version: 0.1.1
Description: ExecutionPlan dataclass and build_plan factory.
License: LGPL-3.0-or-later
"""
from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

from ASOkai._pipeline.base import Runnable
from ASOkai._pipeline.contracts.files import FileInput, FileOutput
from ASOkai._pipeline.steps.base import Step
from ASOkai._pipeline.tasks.base import Task
from ASOkai._pipeline.workflows.base import Workflow

logger = logging.getLogger(__name__)


@dataclass
class ExecutionPlan:
    """Describes exactly what needs to run and what is already done."""

    steps_to_run: list[Step]
    pre_resolved: dict[FileOutput, Path] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _flatten_runnable(
    runnable: Runnable,
    _seen: frozenset[str] = frozenset(),
) -> list[Step]:
    """Expand any Runnable to an ordered list of Steps."""
    if isinstance(runnable, Workflow):
        if runnable.name in _seen:
            raise ValueError(f"Workflow '{runnable.name}' participates in a cycle.")
        seen = _seen | {runnable.name}
        out: list[Step] = []
        for member in runnable.members:
            out.extend(_flatten_runnable(member, seen))
        return out
    if isinstance(runnable, Task):
        return list(runnable.steps)
    if isinstance(runnable, Step):
        return [runnable]
    raise TypeError(
        f"Unsupported runnable type: {type(runnable).__name__!r}."
    )


def _dependency_inputs(step: Step, config: dict) -> list[FileInput]:
    """Return file inputs whose producer has not been replaced by an override."""
    return [
        file_input
        for file_input in step.spec.inputs
        if file_input.configured_override_path(config) is None
    ]


def _topo_sort(steps: list[Step], config: dict) -> list[Step]:
    """
    Return a dep-first topological ordering of the given steps.

    Only edges to steps present in this plan are followed. Dependencies outside
    the plan are validated before sorting and represented via pre_resolved.
    Raises ValueError on cycles.
    """
    by_name = {s.name: s for s in steps}
    result: list[Step] = []
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(step: Step) -> None:
        if step.name in visited:
            return
        if step.name in visiting:
            raise ValueError(
                f"Dependency cycle detected involving step '{step.name}'."
            )
        visiting.add(step.name)
        for file_input in _dependency_inputs(step, config):
            dep_name = file_input.source.producer
            dep = by_name.get(dep_name)
            if dep is not None:
                visit(dep)
        visiting.discard(step.name)
        visited.add(step.name)
        result.append(step)

    for step in steps:
        visit(step)

    return result


def _collect_transitive_deps(
    steps: list[Step],
    registry: dict[str, Step],
    config: dict,
) -> list[Step]:
    """
    Starting from *steps*, walk each step's dependencies recursively and
    return the union (deduplicated, first-seen order, registry-resolved).
    Unknown dependency names raise ValueError.
    """
    seen: set[str] = {s.name for s in steps}
    result: list[Step] = list(steps)

    queue: deque[Step] = deque(steps)
    while queue:
        current = queue.popleft()
        for file_input in _dependency_inputs(current, config):
            dep_name = file_input.source.producer
            if dep_name in seen:
                continue
            dep = registry.get(dep_name)
            if dep is None:
                raise ValueError(
                    f"Step '{current.name}' depends on unknown step '{dep_name}'."
                )
            seen.add(dep_name)
            result.append(dep)
            queue.append(dep)

    return result


def _resolve_external_deps(
    steps: list[Step],
    registry: dict[str, Step],
    config: dict,
) -> dict[FileOutput, Path]:
    """
    Validate deps outside the current plan and reuse completed outputs.

    If a dependency is not included in *steps*, it must exist in the registry and
    already have outputs on disk. Otherwise the caller should use recursive=True.
    """
    by_name = {s.name: s for s in steps}
    pre_resolved: dict[FileOutput, Path] = {}

    for step in steps:
        for file_input in _dependency_inputs(step, config):
            source = file_input.source
            producer = source.producer
            dep = by_name.get(producer) or registry.get(producer)
            if dep is None:
                raise ValueError(
                    f"Step '{step.name}' references unknown producer "
                    f"'{producer}'."
                )
            try:
                declared = dep.spec.output(source.name)
            except KeyError as error:
                raise ValueError(
                    f"Step '{step.name}' input '{file_input.name}' references "
                    f"unknown output '{source.name}' on step '{producer}'."
                ) from error
            if declared is not source:
                raise ValueError(
                    f"Step '{step.name}' input '{file_input.name}' references "
                    f"an output declaration that does not belong to '{producer}'."
                )

            if producer in by_name:
                continue

            if not dep.outputs_exist(config):
                raise RuntimeError(
                    f"Step '{step.name}' requires '{producer}' but its outputs "
                    f"are missing. Run '{producer}' first, or use --recursive "
                    "to run dependencies automatically."
                )

            pre_resolved[source] = dep.validated_output_paths(config)[source.name]
            logger.debug(
                "[plan] dependency '%s/%s' exists — pre-resolved.",
                producer,
                source.name,
            )

    return pre_resolved


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_plan(
    runnables: list[Runnable],
    config: dict,
    *,
    recursive: bool = False,
    force: bool = False,
    _registry: dict[str, Step] | None = None,
) -> ExecutionPlan:
    """
    Build an ExecutionPlan from an arbitrary list of Runnables.

    Steps:
    1. Flatten each Runnable to Step objects.
    2. Deduplicate by name, preserving first-seen order.
    3. Remove dependency edges replaced by configured file overrides.
    4. If recursive=True, prepend any missing transitive dependencies from
       the step registry.
    5. Validate external dependencies and reuse completed dep outputs.
    6. Topologically sort (dep-first DFS).
    7. Partition: steps whose outputs already exist (and force=False) go into
       pre_resolved; the rest go into steps_to_run.
    """
    if _registry is None:
        from ASOkai.Plugins._registry import get_steps
        _registry = get_steps()

    # 1 + 2: flatten and deduplicate
    seen_names: set[str] = set()
    flat: list[Step] = []
    for runnable in runnables:
        for step in _flatten_runnable(runnable):
            if step.name not in seen_names:
                seen_names.add(step.name)
                flat.append(step)

    # 3 + 4: remove overridden edges and collect active transitive deps
    if recursive:
        flat = _collect_transitive_deps(flat, _registry, config)

    # 5: validate deps not included in the plan and reuse completed outputs
    pre_resolved = _resolve_external_deps(
        flat,
        _registry,
        config,
    )

    # 6: topological sort
    ordered = _topo_sort(flat, config)

    # 7: partition
    steps_to_run: list[Step] = []

    for step in ordered:
        if not force and step.outputs_exist(config):
            for key, path in step.validated_output_paths(config).items():
                pre_resolved[step.spec.output(key)] = path
            logger.debug("[plan] '%s' outputs exist — pre-resolved.", step.name)
        else:
            steps_to_run.append(step)

    return ExecutionPlan(steps_to_run=steps_to_run, pre_resolved=pre_resolved)
