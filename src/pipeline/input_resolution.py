"""
Filename: src/pipeline/input_resolution.py
Description: Resolve step config, dependency, override, and output inputs.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pipeline import config as cfg
from pipeline.base import Step
from pipeline.registry import get_steps


InputSource = Literal[
    "scalar",
    "dep_wired",
    "dep_disk",
    "input_override",
    "output_path",
]


@dataclass
class ResolvedInput:
    """
    An input value annotated with its resolution source.

    ``cwl_value`` is what gets passed to the executor. It is ``None`` for inputs
    that are wired internally between steps in a generated CWL workflow and
    therefore do not appear in the top-level inputs JSON.
    """

    cwl_value: Any
    source: InputSource
    path: Path | None = None
    dep_name: str | None = None
    config_path: str | None = None


def resolve_step_inputs(
    step: Step,
    config: dict,
    *,
    pre_resolved: dict[str, Path] | None = None,
    steps_in_plan: set[str] | None = None,
) -> dict[str, ResolvedInput]:
    """
    Resolve all inputs for *step* and return them annotated with their source.

    Priority, highest first:
    1. input_overrides when the config dot-path is present.
    2. dependency outputs, either internally wired or passed as File inputs.
    3. scalar config_map values.
    """
    if pre_resolved is None:
        pre_resolved = {}
    if steps_in_plan is None:
        steps_in_plan = set()

    resolved: dict[str, ResolvedInput] = {}

    for cwl_key, config_path in step.config_map.items():
        try:
            resolved[cwl_key] = ResolvedInput(
                cwl_value=cfg.resolve(config, config_path),
                source="scalar",
                config_path=config_path,
            )
        except KeyError:
            pass

    registry = get_steps()
    for dep_name in step.dependencies:
        dep = registry.get(dep_name)
        if dep is None:
            continue
        for out_key, disk_path in dep.output_paths(config).items():
            if dep_name in steps_in_plan:
                resolved[out_key] = ResolvedInput(
                    cwl_value=None,
                    source="dep_wired",
                    dep_name=dep_name,
                )
            elif out_key in pre_resolved:
                p = pre_resolved[out_key]
                resolved[out_key] = ResolvedInput(
                    cwl_value={"class": "File", "path": str(p.resolve())},
                    source="dep_disk",
                    path=p,
                    dep_name=dep_name,
                )
            else:
                resolved[out_key] = ResolvedInput(
                    cwl_value={"class": "File", "path": str(disk_path.resolve())},
                    source="dep_disk",
                    path=disk_path,
                    dep_name=dep_name,
                )

    for cwl_key, config_path in getattr(step, "input_overrides", {}).items():
        try:
            p = Path(cfg.resolve(config, config_path)).resolve()
            resolved[cwl_key] = ResolvedInput(
                cwl_value={"class": "File", "path": str(p)},
                source="input_override",
                path=p,
                config_path=config_path,
            )
        except KeyError:
            pass

    if getattr(step, "output_inputs", None) != {}:
        for out_key, path in step.output_paths(config).items():
            resolved[f"{out_key}_output"] = ResolvedInput(
                cwl_value=path.name,
                source="output_path",
                path=path,
            )

    return resolved


def to_cwl_inputs(resolved: dict[str, ResolvedInput]) -> dict[str, Any]:
    """Strip annotations and exclude internally wired inputs."""
    return {k: ri.cwl_value for k, ri in resolved.items() if ri.cwl_value is not None}


def resolve_step_sequence_inputs(
    step_objs: list[Step],
    config: dict,
    pre_resolved: dict[str, Path],
) -> dict[str, Any]:
    """
    Collect top-level inputs for a generated multi-step CWL workflow.

    Internally wired inputs are excluded.
    """
    steps_in_plan = {s.name for s in step_objs}
    merged: dict[str, Any] = {}
    for step in step_objs:
        resolved = resolve_step_inputs(
            step,
            config,
            pre_resolved=pre_resolved,
            steps_in_plan=steps_in_plan,
        )
        for key, ri in resolved.items():
            if key not in merged and ri.cwl_value is not None:
                merged[key] = ri.cwl_value
    return merged

