"""
Filename: src/pipeline/cwl_generation.py
Description: Generate multi-step CWL workflow documents from pipeline steps.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from pipeline.base import Step
from pipeline.registry import get_steps


def _cwl_step_id(step_name: str) -> str:
    """Return a CWL-safe step id for a registry step name."""
    return step_name.replace("-", "_")


def _output_names(step: Step, config: dict) -> tuple[str, ...]:
    """Return CWL output names from the step's configured output paths."""
    return tuple(step.output_paths(config).keys())


def generate_cwl(
    step_objs: list[Step],
    pre_resolved: dict[str, Path],
    config: dict,
) -> str:
    """
    Build a CWL Workflow document that wires together the given steps.

    Wire-up rules:
    - pre_resolved keys become top-level ``File`` inputs.
    - input_overrides not covered by an in-sequence dependency become ``File?``.
    - config_map values become top-level scalar inputs.
    - generated workflow outputs come from the final step only.
    """
    step_by_name = {s.name: s for s in step_objs}
    step_names_in_seq = set(step_by_name)

    dep_output_names_in_seq: set[str] = set()
    for step in step_objs:
        for dep_name in step.dependencies:
            if dep_name in step_names_in_seq:
                dep_output_names_in_seq.update(
                    _output_names(step_by_name[dep_name], config)
                )

    all_inputs: dict[str, str | dict[str, Any]] = {}

    for key in pre_resolved:
        all_inputs[key] = "File"

    for step in step_objs:
        for cwl_key in getattr(step, "input_overrides", {}):
            if cwl_key not in all_inputs and cwl_key not in dep_output_names_in_seq:
                all_inputs[cwl_key] = "File?"

    for step in step_objs:
        for cwl_key in step.config_map:
            if cwl_key not in all_inputs:
                all_inputs[cwl_key] = "string"

    for step in step_objs:
        if getattr(step, "output_inputs", None) != {}:
            for out_key in _output_names(step, config):
                all_inputs.setdefault(f"{out_key}_output", "string")

    cwl_steps = {}
    for step in step_objs:
        in_map: dict[str, str | dict] = {}

        for cwl_key in step.config_map:
            in_map[cwl_key] = cwl_key

        for cwl_key in getattr(step, "input_overrides", {}):
            if cwl_key not in in_map:
                in_map[cwl_key] = cwl_key

        if getattr(step, "output_inputs", None) != {}:
            for out_key in _output_names(step, config):
                cwl_input_key = f"{out_key}_output"
                in_map[cwl_input_key] = cwl_input_key

        for dep_name in step.dependencies:
            if dep_name not in step_names_in_seq:
                dep_step = step_by_name.get(dep_name) or get_steps().get(dep_name)
                if dep_step is None:
                    continue
                for out_key in _output_names(dep_step, config):
                    if out_key in pre_resolved:
                        in_map[out_key] = out_key
                continue

            dep_step = step_by_name[dep_name]
            dep_cwl_id = _cwl_step_id(dep_name)
            for out_key in _output_names(dep_step, config):
                if out_key in pre_resolved:
                    in_map[out_key] = out_key
                else:
                    in_map[out_key] = f"{dep_cwl_id}/{out_key}"

        cwl_steps[_cwl_step_id(step.name)] = {
            "run": step.cwl_path,
            "in": in_map,
            "out": list(_output_names(step, config)),
        }

    last_step = step_objs[-1]
    last_id = _cwl_step_id(last_step.name)
    cwl_outputs = {
        key: {"type": "File", "outputSource": f"{last_id}/{key}"}
        for key in _output_names(last_step, config)
    }

    doc = {
        "cwlVersion": "v1.2",
        "class": "Workflow",
        "inputs": all_inputs,
        "steps": cwl_steps,
        "outputs": cwl_outputs,
    }
    return yaml.dump(doc, default_flow_style=False, sort_keys=False)
