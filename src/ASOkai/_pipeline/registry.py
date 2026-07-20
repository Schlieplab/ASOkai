#!/usr/bin/env python
"""
Filename: src/ASOkai/_pipeline/registry.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Version: 0.1.1
Description: Registry for pipeline steps, tasks, and workflows.
License: LGPL-3.0-or-later
"""
from __future__ import annotations

from importlib.metadata import entry_points

from ASOkai._pipeline.base import Step, Task, Workflow
from ASOkai._pipeline.steps.download_genome import DownloadGenomeStep
from ASOkai._pipeline.steps.create_target_gene import CreateTargetGeneStep
from ASOkai._pipeline.steps.generate_antisense_candidates import (
    GenerateAntisenseCandidatesStep,
)
from ASOkai._pipeline.steps.intrinsic_features import IntrinsicFeaturesStep
from ASOkai._pipeline.tasks.instantiate_target_gene import InstantiateTargetGeneTask
from ASOkai._pipeline.workflows.standard import StandardWorkflow

_BUILTIN_STEPS: list[Step] = [
    DownloadGenomeStep(),
    CreateTargetGeneStep(),
    GenerateAntisenseCandidatesStep(),
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
