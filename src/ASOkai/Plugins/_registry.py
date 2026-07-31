#!/usr/bin/env python
"""
Filename: src/ASOkai/Plugins/_registry.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Version: 0.1.1
Description: Discovery registry for built-in and external extensions.
License: LGPL-3.0-or-later
"""
from __future__ import annotations

from importlib.metadata import entry_points
from os import PathLike
from pathlib import Path

from ASOkai._pipeline.steps.analysis.intrinsic_features import (
    IntrinsicFeaturesStep,
)
from ASOkai._pipeline.steps.base import Step
from ASOkai._pipeline.steps.core.create_target_gene import CreateTargetGeneStep
from ASOkai._pipeline.steps.core.download_genome import DownloadGenomeStep
from ASOkai._pipeline.steps.core.generate_antisense_candidates import (
    GenerateAntisenseCandidatesStep,
)
from ASOkai._pipeline.tasks.base import Task
from ASOkai._pipeline.tasks.instantiate_target_gene import InstantiateTargetGeneTask
from ASOkai._pipeline.workflows.base import Workflow
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


def _index_unique(kind: str, instances: list) -> dict:
    """Index registered objects by name without allowing silent replacement."""
    result = {}
    for instance in instances:
        if instance.name in result:
            raise ValueError(
                f"Duplicate registered {kind} name: {instance.name!r}."
            )
        result[instance.name] = instance
    return result


def get_steps() -> dict[str, Step]:
    return _index_unique(
        "step",
        [*_BUILTIN_STEPS, *_load_plugins("asokai.steps")],
    )


def get_tasks() -> dict[str, Task]:
    return _index_unique(
        "task",
        [*_BUILTIN_TASKS, *_load_plugins("asokai.tasks")],
    )


def get_workflows() -> dict[str, Workflow]:
    return _index_unique(
        "workflow",
        [*_BUILTIN_WORKFLOWS, *_load_plugins("asokai.workflows")],
    )


def get_config_schema_paths() -> dict[str, Path]:
    """Return config schema files registered by installed plugins."""
    schemas: dict[str, Path] = {}
    for entry_point in entry_points(group="asokai.config_schemas"):
        if entry_point.name in schemas:
            raise ValueError(
                "Duplicate registered config schema name: "
                f"{entry_point.name!r}."
            )
        value = entry_point.load()
        if not isinstance(value, (str, PathLike)):
            raise ValueError(
                f"Plugin config schema '{entry_point.name}' must expose "
                "a file path."
            )
        schemas[entry_point.name] = Path(value)
    return schemas
