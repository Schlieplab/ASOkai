"""
Filename: src/pipeline/registry.py
Description: Registry for pipeline steps, tasks, and workflows.
             Discovers built-in units and any installed plugins via entry points.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

from importlib.metadata import entry_points

from pipeline.base import Step, Task, Workflow
from pipeline.steps.download_genome import DownloadGenomeStep
from pipeline.steps.create_target_gene import CreateTargetGeneStep
from pipeline.steps.intrinsic_features import IntrinsicFeaturesStep
from pipeline.tasks.instantiate_target_gene import InstantiateTargetGeneTask
from pipeline.workflows.standard import StandardWorkflow

_BUILTIN_STEPS: list[Step] = [
    DownloadGenomeStep(),
    CreateTargetGeneStep(),
    IntrinsicFeaturesStep(),
]

_BUILTIN_TASKS: list[Task] = [
    InstantiateTargetGeneTask(),
]

_BUILTIN_WORKFLOWS: list[Workflow] = [
    StandardWorkflow(),
]


def _load_plugins(group: str) -> list:
    instances = []
    for ep in entry_points(group=group):
        cls = ep.load()
        instances.append(cls())
    return instances


def get_steps() -> dict[str, Step]:
    steps = {s.name: s for s in _BUILTIN_STEPS}
    steps.update({s.name: s for s in _load_plugins("asokai.steps")})
    return steps


def get_tasks() -> dict[str, Task]:
    tasks = {t.name: t for t in _BUILTIN_TASKS}
    tasks.update({t.name: t for t in _load_plugins("asokai.tasks")})
    return tasks


def get_workflows() -> dict[str, Workflow]:
    workflows = {w.name: w for w in _BUILTIN_WORKFLOWS}
    workflows.update({w.name: w for w in _load_plugins("asokai.workflows")})
    return workflows
