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

from ASOkai._pipeline.base import Runnable, Step, Task, Workflow

logger = logging.getLogger(__name__)


@dataclass
class ExecutionPlan:
    """Describes exactly what needs to run and what is already done."""

    steps_to_run: list[Step]
    pre_resolved: dict[str, Path] = field(default_factory=dict)


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


def _topo_sort(steps: list[Step]) -> list[Step]:
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
        for dep_name in step.dependencies:
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
        for dep_name in current.dependencies:
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
) -> dict[str, Path]:
    """
    Validate deps outside the current plan and reuse completed outputs.

    If a dependency is not included in *steps*, it must exist in the registry and
    already have outputs on disk. Otherwise the caller should use recursive=True.
    """
    by_name = {s.name: s for s in steps}
    pre_resolved: dict[str, Path] = {}

    for step in steps:
        for dep_name in step.dependencies:
            if dep_name in by_name:
                continue

            dep = registry.get(dep_name)
            if dep is None:
                raise ValueError(
                    f"Step '{step.name}' depends on unknown step '{dep_name}'."
                )
            if not dep.outputs_exist(config):
                raise RuntimeError(
                    f"Step '{step.name}' requires '{dep_name}' but its outputs are missing. "
                    f"Run '{dep_name}' first, or use --recursive to run dependencies automatically."
                )

            for key, path in dep.validated_output_paths(config).items():
                pre_resolved[key] = path
            logger.debug("[plan] dependency '%s' outputs exist — pre-resolved.", dep_name)

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
    3. If recursive=True, prepend any missing transitive dependencies from
       the step registry.
    4. Validate external dependencies and reuse completed dep outputs.
    5. Topologically sort (dep-first DFS).
    6. Partition: steps whose outputs already exist (and force=False) go into
       pre_resolved; the rest go into steps_to_run.
    """
    if _registry is None:
        from ASOkai._pipeline.registry import get_steps
        _registry = get_steps()

    # 1 + 2: flatten and deduplicate
    seen_names: set[str] = set()
    flat: list[Step] = []
    for runnable in runnables:
        for step in _flatten_runnable(runnable):
            if step.name not in seen_names:
                seen_names.add(step.name)
                flat.append(step)

    # 3: collect transitive deps when recursive
    if recursive:
        flat = _collect_transitive_deps(flat, _registry)

    # 4: validate deps not included in the plan and reuse completed outputs
    pre_resolved = _resolve_external_deps(
        flat,
        _registry,
        config,
    )

    # 5: topological sort
    ordered = _topo_sort(flat)

    # 6: partition
    steps_to_run: list[Step] = []

    for step in ordered:
        if not force and step.outputs_exist(config):
            for key, path in step.validated_output_paths(config).items():
                pre_resolved[key] = path
            logger.debug("[plan] '%s' outputs exist — pre-resolved.", step.name)
        else:
            steps_to_run.append(step)

    return ExecutionPlan(steps_to_run=steps_to_run, pre_resolved=pre_resolved)
