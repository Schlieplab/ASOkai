#!/usr/bin/env python
"""
Filename: docs/source/_extensions/contract_docs/runnables.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Generated references for built-in tasks and workflows.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

from typing import Any

from docutils import nodes
from sphinx import addnodes
from sphinx.util.docutils import SphinxDirective

from .rendering import (
    details,
    document_link,
    note_reference_dependencies,
    section,
    table,
)


def get_built_in_runnables(kind: str) -> tuple[Any, ...]:
    """Return built-in tasks or workflows in registry order."""
    from ASOkai._pipeline.catalog import (
        _BUILTIN_TASKS,
        _BUILTIN_WORKFLOWS,
    )

    registries = {
        "task": _BUILTIN_TASKS,
        "workflow": _BUILTIN_WORKFLOWS,
    }
    try:
        return tuple(registries[kind])
    except KeyError as error:
        expected = ", ".join(registries)
        raise ValueError(
            f"Unknown runnable kind {kind!r}; expected one of: {expected}."
        ) from error


def get_built_in_runnable(kind: str, name: str) -> Any:
    """Return one named built-in task or workflow."""
    for runnable in get_built_in_runnables(kind):
        if runnable.name == name:
            return runnable
    raise ValueError(f"Unknown built-in {kind}: {name!r}.")


def _runnable_documentation_sources() -> list[object]:
    """Return declarations whose values feed runnable references."""
    from ASOkai._pipeline import catalog

    return [
        catalog,
        *catalog._BUILTIN_STEPS,
        *catalog._BUILTIN_TASKS,
        *catalog._BUILTIN_WORKFLOWS,
    ]


def _runnable_kind(runnable: Any) -> str:
    from ASOkai._pipeline.steps.base import Step
    from ASOkai._pipeline.tasks.base import Task
    from ASOkai._pipeline.workflows.base import Workflow

    if isinstance(runnable, Step):
        return "step"
    if isinstance(runnable, Task):
        return "task"
    if isinstance(runnable, Workflow):
        return "workflow"
    raise TypeError(f"Unsupported pipeline unit: {type(runnable).__name__}.")


def _reference_target(runnable: Any) -> str:
    kind = _runnable_kind(runnable)
    return f"{kind}s/{runnable.name}"


def _runnable_link(runnable: Any, *, refdoc: str) -> addnodes.pending_xref:
    return document_link(
        _reference_target(runnable),
        runnable.name,
        refdoc=refdoc,
    )


def build_runnable_list(
    kind: str, *, category: str | None = None, refdoc: str = ""
) -> nodes.bullet_list:
    """Build a linked list of built-in tasks or workflows, optionally grouped."""
    from ASOkai._pipeline.tasks.base import task_category

    if category is not None and (
        kind != "task" or category not in {"core", "analysis", "utils", "pipeline"}
    ):
        raise ValueError(f"Unknown {kind} category: {category!r}.")
    result = nodes.bullet_list()
    for runnable in get_built_in_runnables(kind):
        if category is not None and task_category(runnable) != category:
            continue
        item = nodes.list_item()
        paragraph = nodes.paragraph()
        paragraph += _runnable_link(runnable, refdoc=refdoc)
        paragraph += nodes.Text(f" — {runnable.description}")
        item += paragraph
        result += item
    return result


def build_analysis_list(*, refdoc: str = "") -> nodes.bullet_list:
    """List built-in analysis steps and explicitly categorized analysis tasks."""
    from ASOkai._pipeline.catalog import _BUILTIN_STEPS, _BUILTIN_TASKS
    from ASOkai._pipeline.steps.analysis.base import AnalysisStep
    from ASOkai._pipeline.tasks.base import task_category

    analyses: list[Any] = [
        step
        for step in _BUILTIN_STEPS
        if isinstance(step, AnalysisStep) and step.listed
    ]
    analyses.extend(
        task
        for task in _BUILTIN_TASKS
        if task_category(task) == "analysis"
    )
    result = nodes.bullet_list()
    for runnable in sorted(analyses, key=lambda item: item.name):
        item = nodes.list_item()
        paragraph = nodes.paragraph()
        paragraph += _runnable_link(runnable, refdoc=refdoc)
        paragraph += nodes.Text(f" ({_runnable_kind(runnable)}) — {runnable.description}")
        item += paragraph
        result += item
    return result


def _identity(kind: str) -> nodes.field_list:
    identity = nodes.field_list()
    field = nodes.field()
    field += nodes.field_name(text="Pipeline unit")
    body = nodes.field_body()
    body += nodes.paragraph(text=kind.capitalize())
    field += body
    identity += field
    return identity


def _run_section(runnable: Any, kind: str) -> nodes.section:
    option = "--workflow" if kind == "workflow" else "--task"
    command = (
        f"ASOkai run {option} {runnable.name} "
        "--config-file ./config.yaml"
    )
    return section(
        f"Run this {kind}",
        [
            nodes.literal_block(command, command),
            nodes.paragraph(
                text=(
                    "ASOkai resolves and schedules missing dependencies "
                    "automatically. Existing valid outputs and configured "
                    "input overrides are reused."
                )
            ),
        ],
    )


def _members(runnable: Any, kind: str) -> list[Any]:
    return list(runnable.steps if kind == "task" else runnable.members)


def _members_section(
    runnable: Any,
    kind: str,
    *,
    refdoc: str,
) -> nodes.section:
    rows = []
    for member in _members(runnable, kind):
        member_name = nodes.paragraph()
        member_name += _runnable_link(member, refdoc=refdoc)
        rows.append(
            (
                member_name,
                details(
                    (
                        ("Type", _runnable_kind(member).capitalize(), False),
                        ("Description", member.description, False),
                    )
                ),
            )
        )
    title = "Steps" if kind == "task" else "Direct members"
    return section(
        title,
        [
            table(
                ("Pipeline unit", "Details"),
                rows,
                (25, 75),
                css_class=f"asokai-{kind}-members",
            )
        ],
    )


def _expanded_steps(runnable: Any) -> list[Any]:
    """Return the unique explicit steps produced by runnable expansion."""
    from ASOkai._pipeline.base import expand_runnable_steps

    return list(
        {step.name: step for step in expand_runnable_steps(runnable)}.values()
    )


def _expanded_steps_section(runnable: Any, *, refdoc: str) -> nodes.section:
    step_list = nodes.bullet_list()
    for step in _expanded_steps(runnable):
        item = nodes.list_item()
        paragraph = nodes.paragraph()
        paragraph += _runnable_link(step, refdoc=refdoc)
        paragraph += nodes.Text(f" — {step.description}")
        item += paragraph
        step_list += item
    return section(
        "Expanded steps",
        [
            nodes.paragraph(
                text=(
                    "Nested tasks and workflows explicitly include these "
                    "steps. Dependency planning may additionally resolve "
                    "upstream steps needed to run them."
                )
            ),
            step_list,
        ],
    )


def build_runnable_reference(
    runnable: Any,
    kind: str,
    *,
    refdoc: str = "",
) -> list[nodes.Node]:
    """Build the reference nodes for one built-in task or workflow."""
    if _runnable_kind(runnable) != kind:
        raise TypeError(
            f"{runnable.name!r} is not a {kind}; "
            f"received {_runnable_kind(runnable)}."
        )
    result: list[nodes.Node] = [
        nodes.paragraph(text=runnable.description),
        _identity(kind),
        _run_section(runnable, kind),
        _members_section(runnable, kind, refdoc=refdoc),
    ]
    if kind == "workflow":
        result.append(_expanded_steps_section(runnable, refdoc=refdoc))
    return result


class ASOkaiRunnableReference(SphinxDirective):
    """Render one built-in task or workflow from the runtime registry."""

    required_arguments = 2

    def run(self) -> list[nodes.Node]:
        try:
            kind, name = self.arguments
            runnable = get_built_in_runnable(kind, name)
            result = build_runnable_reference(
                runnable,
                kind,
                refdoc=self.env.docname,
            )
        except (TypeError, ValueError) as error:
            raise self.error(str(error)) from error
        note_reference_dependencies(
            self.env,
            _runnable_documentation_sources(),
        )
        return result


class ASOkaiRunnableList(SphinxDirective):
    """Render links to built-in tasks or workflows from the registry."""

    required_arguments = 1
    optional_arguments = 1

    def run(self) -> list[nodes.Node]:
        try:
            category = self.arguments[1] if len(self.arguments) > 1 else None
            runnable_list = build_runnable_list(
                self.arguments[0],
                category=category,
                refdoc=self.env.docname,
            )
            result: list[nodes.Node] = [runnable_list]
            if category is not None and not len(runnable_list):
                result = [
                    nodes.paragraph(text="No built-in tasks in this category yet.")
                ]
        except ValueError as error:
            raise self.error(str(error)) from error
        note_reference_dependencies(
            self.env,
            _runnable_documentation_sources(),
        )
        return result


class ASOkaiAnalysisList(SphinxDirective):
    """Render one index of built-in analysis steps and analysis tasks."""

    def run(self) -> list[nodes.Node]:
        result: list[nodes.Node] = [build_analysis_list(refdoc=self.env.docname)]
        note_reference_dependencies(
            self.env,
            _runnable_documentation_sources(),
        )
        return result
