#!/usr/bin/env python
"""
Filename: src/ASOkai/_pipeline/catalog.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Catalog of built-in and installed pipeline components.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib.metadata import entry_points
from os import PathLike
from pathlib import Path
from typing import Any, Sequence

from ASOkai._pipeline.steps.analysis.intrinsic_features import (
    IntrinsicFeaturesStep,
)
from ASOkai._pipeline.steps.base import Step
from ASOkai._pipeline.steps.core.build_genome_kmer_index import (
    BuildGenomeKmerIndexStep,
)
from ASOkai._pipeline.steps.core.create_target_gene import CreateTargetGeneStep
from ASOkai._pipeline.steps.core.download_genome import DownloadGenomeStep
from ASOkai._pipeline.steps.core.generate_aso_candidates import (
    GenerateASOCandidatesStep,
)
from ASOkai._pipeline.tasks.base import Task
from ASOkai._pipeline.tasks.instantiate_target_gene import InstantiateTargetGeneTask
from ASOkai._pipeline.workflows.base import Workflow
from ASOkai._pipeline.workflows.standard import StandardWorkflow

from ASOkai._pipeline.validation import (
    ComponentKind,
    validate_component,
    validate_step_dependencies,
    validate_task_members,
    validate_workflow_members,
)

# Built-in step registry
_BUILTIN_STEPS: tuple[Step, ...] = (
    DownloadGenomeStep(),
    BuildGenomeKmerIndexStep(),
    CreateTargetGeneStep(),
    GenerateASOCandidatesStep(),
    IntrinsicFeaturesStep(),
)

# Built-in task registry
_BUILTIN_TASKS: tuple[Task, ...] = (InstantiateTargetGeneTask(),)

# Built-in workflow registry
_BUILTIN_WORKFLOWS: tuple[Workflow, ...] = (StandardWorkflow(),)


@dataclass(frozen=True)
class _DiscoveredPlugin:
    instance: Any
    source: str
    package_name: str | None


@dataclass(frozen=True)
class _DiscoveredConfigSchema:
    name: str
    path: Path
    package_name: str | None


@dataclass(frozen=True)
class PipelineCatalog:
    """One consistent snapshot of available pipeline components."""

    steps: dict[str, Step]
    tasks: dict[str, Task]
    workflows: dict[str, Workflow]
    config_schema_paths: dict[str, Path]


def _entry_point_package_name(entry_point: Any) -> str | None:
    """Return the installed package that declared an entry point."""
    distribution = getattr(entry_point, "dist", None)
    package_name = getattr(distribution, "name", None)
    return package_name if isinstance(package_name, str) else None


def _entry_point_source(entry_point: Any) -> str:
    """Describe an entry point using its name and installed package."""
    source = repr(entry_point.name)
    package_name = _entry_point_package_name(entry_point)
    if package_name:
        source += f" from package {package_name!r}"
    return source


def _load_entry_point(entry_point: Any, kind: str) -> Any:
    """Load one entry-point value with plugin-specific error context."""
    try:
        return entry_point.load()
    except Exception as error:
        raise ValueError(
            f"Could not load ASOkai {kind} plugin "
            f"{_entry_point_source(entry_point)}: {error}"
        ) from error


def _discover_plugins(
    group: str,
    kind: ComponentKind,
) -> list[_DiscoveredPlugin]:
    """Load, instantiate, and validate plugins from one entry-point group."""
    discovered: list[_DiscoveredPlugin] = []
    for entry_point in entry_points(group=group):
        source = _entry_point_source(entry_point)
        plugin_class = _load_entry_point(entry_point, kind)
        if not isinstance(plugin_class, type):
            raise ValueError(
                f"Invalid ASOkai {kind} plugin {source}: "
                "the entry point must expose a class."
            )
        try:
            instance = plugin_class()
        except Exception as error:
            raise ValueError(
                f"Could not instantiate ASOkai {kind} plugin {source} "
                f"without arguments: {error}"
            ) from error
        try:
            validate_component(kind, instance)
        except (TypeError, ValueError) as error:
            raise ValueError(
                f"Invalid ASOkai {kind} plugin {source}: {error}"
            ) from error
        if instance.name != entry_point.name:
            raise ValueError(
                f"Invalid ASOkai {kind} plugin {source}: entry-point name "
                f"must match the declared name {instance.name!r}."
            )
        discovered.append(
            _DiscoveredPlugin(
                instance,
                source,
                _entry_point_package_name(entry_point),
            )
        )
    return discovered


def _discover_config_schemas() -> list[_DiscoveredConfigSchema]:
    """Load configuration schema paths with their package ownership."""
    from ASOkai._pipeline import config

    discovered: list[_DiscoveredConfigSchema] = []
    names: set[str] = set()
    for entry_point in entry_points(group="asokai.config_schemas"):
        if entry_point.name in names:
            raise ValueError(
                "Duplicate registered config schema name: " f"{entry_point.name!r}."
            )
        names.add(entry_point.name)
        value = _load_entry_point(entry_point, "config schema")
        if not isinstance(value, (str, PathLike)):
            raise ValueError(
                f"Invalid ASOkai config schema plugin "
                f"{_entry_point_source(entry_point)}: the entry point must "
                "expose a file path."
            )
        path = Path(value)
        try:
            config.load_config_schema(
                path,
                f"Plugin {entry_point.name!r}",
            )
        except ValueError as error:
            raise ValueError(
                "Invalid ASOkai config schema plugin "
                f"{_entry_point_source(entry_point)}: {error}"
            ) from error
        discovered.append(
            _DiscoveredConfigSchema(
                entry_point.name,
                path,
                _entry_point_package_name(entry_point),
            )
        )
    return discovered


def _index_components(
    kind: ComponentKind,
    builtins: Sequence[Any],
    plugins: Sequence[_DiscoveredPlugin],
) -> dict[str, Any]:
    """Index components and identify both sources of duplicate names."""
    result: dict[str, Any] = {}
    sources: dict[str, str] = {}

    entries = [
        *(
            (instance, f"built-in ASOkai {kind} {instance.name!r}")
            for instance in builtins
        ),
        *(
            (plugin.instance, f"ASOkai {kind} plugin {plugin.source}")
            for plugin in plugins
        ),
    ]
    for instance, source in entries:
        previous_source = sources.get(instance.name)
        if previous_source is not None:
            raise ValueError(
                f"Duplicate registered {kind} name {instance.name!r}: "
                f"{source} conflicts with {previous_source}."
            )
        result[instance.name] = instance
        sources[instance.name] = source
    return result


def _validate_builtin_declarations(
    kind: ComponentKind,
    instances: Sequence[object],
) -> None:
    """Validate declarations for components provided by ASOkai."""
    for instance in instances:
        try:
            validate_component(kind, instance)
        except (TypeError, ValueError) as error:
            name = getattr(instance, "name", type(instance).__name__)
            raise ValueError(
                f"Invalid built-in ASOkai {kind} {name!r}: {error}"
            ) from error


def _validation_context(
    kind: ComponentKind,
    instance: Any,
    plugins: list[_DiscoveredPlugin],
) -> str:
    """Describe a registered declaration without losing plugin provenance."""
    for plugin in plugins:
        if plugin.instance is instance:
            return f"Invalid ASOkai {kind} plugin {plugin.source}"
    return f"Invalid built-in ASOkai {kind} {instance.name!r}"


_validate_builtin_declarations("step", _BUILTIN_STEPS)
_validate_builtin_declarations("task", _BUILTIN_TASKS)
_validate_builtin_declarations("workflow", _BUILTIN_WORKFLOWS)


def _build_step_registry(
    plugins: list[_DiscoveredPlugin],
    config_schemas: list[_DiscoveredConfigSchema],
) -> dict[str, Step]:
    """Validate and index built-in and already-discovered steps."""
    registered = _index_components(
        "step",
        _BUILTIN_STEPS,
        plugins,
    )
    for step in registered.values():
        try:
            validate_step_dependencies(step, registered)
        except (TypeError, ValueError) as error:
            raise ValueError(
                f"{_validation_context('step', step, plugins)}: {error}"
            ) from error

    from ASOkai._pipeline import config

    try:
        config.validate_step_config_paths(_BUILTIN_STEPS)
    except ValueError as error:
        raise ValueError(
            f"Invalid built-in ASOkai step configuration: {error}"
        ) from error

    if plugins:
        for plugin in plugins:
            schema_paths = {
                schema.name: schema.path
                for schema in config_schemas
                if plugin.package_name is not None
                and schema.package_name == plugin.package_name
            }
            try:
                config.validate_step_config_paths(
                    [plugin.instance],
                    schema_paths,
                )
            except ValueError as error:
                raise ValueError(
                    f"Invalid ASOkai step plugin {plugin.source}: {error}"
                ) from error
    return registered


def get_steps() -> dict[str, Step]:
    """Discover and return built-in and installed steps."""
    plugins = _discover_plugins("asokai.steps", "step")
    return _build_step_registry(plugins, _discover_config_schemas())


def get_tasks(
    registered_steps: dict[str, Step] | None = None,
    config_schemas: Sequence[_DiscoveredConfigSchema] | None = None,
) -> dict[str, Task]:
    """Return tasks, reusing an existing step registry when provided."""
    from ASOkai._pipeline import config

    plugins = _discover_plugins("asokai.tasks", "task")
    registered = _index_components(
        "task",
        _BUILTIN_TASKS,
        plugins,
    )
    if registered_steps is None:
        registered_steps = get_steps()
    if config_schemas is None:
        config_schemas = _discover_config_schemas()
    schema_paths = {schema.name: schema.path for schema in config_schemas}
    for task in registered.values():
        try:
            validate_task_members(task, registered_steps)
            config.validate_task_config_paths([task], schema_paths)
        except (TypeError, ValueError) as error:
            raise ValueError(
                f"{_validation_context('task', task, plugins)}: {error}"
            ) from error
    return registered


def get_workflows(
    registered_steps: dict[str, Step] | None = None,
    registered_tasks: dict[str, Task] | None = None,
) -> dict[str, Workflow]:
    """Return workflows, reusing dependency registries when provided."""
    plugins = _discover_plugins("asokai.workflows", "workflow")
    registered = _index_components(
        "workflow",
        _BUILTIN_WORKFLOWS,
        plugins,
    )
    if registered_steps is None:
        registered_steps = get_steps()
    if registered_tasks is None:
        registered_tasks = get_tasks(registered_steps)
    for workflow in registered.values():
        try:
            validate_workflow_members(
                workflow,
                registered_steps,
                registered_tasks,
                registered,
            )
        except (TypeError, ValueError) as error:
            raise ValueError(
                f"{_validation_context('workflow', workflow, plugins)}: " f"{error}"
            ) from error
    return registered


def get_pipeline_catalog() -> PipelineCatalog:
    """Discover every component once and return one validated snapshot."""
    config_schemas = _discover_config_schemas()
    steps = _build_step_registry(
        _discover_plugins("asokai.steps", "step"),
        config_schemas,
    )
    tasks = get_tasks(steps, config_schemas)
    workflows = get_workflows(steps, tasks)
    return PipelineCatalog(
        steps=steps,
        tasks=tasks,
        workflows=workflows,
        config_schema_paths={schema.name: schema.path for schema in config_schemas},
    )


def get_config_schema_paths() -> dict[str, Path]:
    """Return config schema files registered by installed plugins."""
    return {schema.name: schema.path for schema in _discover_config_schemas()}
