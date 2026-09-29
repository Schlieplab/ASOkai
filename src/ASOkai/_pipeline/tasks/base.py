#!/usr/bin/env python
"""
Filename: src/ASOkai/_pipeline/tasks/base.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Contracts for named collections of pipeline step runs.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

from typing import Any, Mapping, Protocol, Sequence, runtime_checkable

from ASOkai._pipeline.base import Runnable, is_valid_runnable_name
from ASOkai._pipeline.contracts.parameters import ScalarParam
from ASOkai._pipeline.steps.base import Step


@runtime_checkable
class Task(Runnable, Protocol):
    """Named step collection, optionally declared as named runs."""

    @property
    def steps(self) -> Sequence[Step]:
        """Expose declared runs to existing catalog and description APIs."""
        return tuple(run["step"] for run in getattr(self, "runs", ()))


def validate_task_parameters(task: Task) -> tuple[ScalarParam, ...]:
    """Validate the scalar parameters exposed by a named task."""
    params = getattr(task, "params", ())
    if isinstance(params, (str, bytes)) or not isinstance(params, Sequence):
        raise TypeError("task params must be a sequence of ScalarParam values.")
    names: set[str] = set()
    for parameter in params:
        if not isinstance(parameter, ScalarParam):
            raise TypeError("task params must contain only ScalarParam values.")
        if not is_valid_runnable_name(parameter.name):
            raise ValueError(
                f"task {task.name!r} parameter name {parameter.name!r} is invalid."
            )
        if parameter.name in names:
            raise ValueError(
                f"task {task.name!r} has duplicate parameter {parameter.name!r}."
            )
        names.add(parameter.name)
    return tuple(params)


def validate_task_runs(task: Task) -> tuple[Mapping[str, Any], ...]:
    """Validate one task's local run names, ports, and links."""
    declared_parameters = {
        parameter.name for parameter in validate_task_parameters(task)
    }
    runs = getattr(task, "runs", None)
    if isinstance(runs, (str, bytes)) or not isinstance(runs, Sequence) or not runs:
        raise TypeError("task runs must be a non-empty sequence.")

    by_id: dict[str, Mapping[str, Any]] = {}
    for run in runs:
        if not isinstance(run, Mapping):
            raise TypeError("task runs must contain only mappings.")
        unknown_fields = set(run) - {"id", "step", "parameters", "inputs"}
        if unknown_fields:
            names = ", ".join(sorted(str(name) for name in unknown_fields))
            raise ValueError(f"task {task.name!r} run has unknown field(s): {names}.")
        run_id = run.get("id")
        if not isinstance(run_id, str) or not is_valid_runnable_name(run_id):
            raise ValueError(f"task {task.name!r} run id must be a valid name.")
        if not isinstance(run.get("step"), Step):
            raise TypeError(f"task {task.name!r} run {run_id!r} step must be a Step.")
        if not isinstance(run.get("parameters", {}), Mapping):
            raise TypeError(
                f"task {task.name!r} run {run_id!r} parameters must be a mapping."
            )
        if not isinstance(run.get("inputs", {}), Mapping):
            raise TypeError(
                f"task {task.name!r} run {run_id!r} inputs must be a mapping."
            )
        if run_id in by_id:
            raise ValueError(f"task {task.name!r} has duplicate run id {run_id!r}.")
        by_id[run_id] = run

    forwarded_parameters: set[str] = set()
    for run in runs:
        run_id = run["id"]
        step = run["step"]
        declared_inputs = {item.name: item for item in step.spec.inputs}
        run_parameters = run.get("parameters", {})
        unknown_parameters = set(run_parameters) - {
            parameter.name for parameter in step.spec.params
        }
        if unknown_parameters:
            names = ", ".join(sorted(str(name) for name in unknown_parameters))
            raise ValueError(
                f"task {task.name!r} run {run_id!r} has unknown "
                f"parameter(s): {names}."
            )
        for value in run_parameters.values():
            if not isinstance(value, Mapping):
                continue
            if set(value) != {"task_parameter"}:
                raise TypeError(
                    f"task {task.name!r} run {run_id!r} parameter references "
                    "must specify only task_parameter."
                )
            name = value["task_parameter"]
            if type(name) is not str or name not in declared_parameters:
                raise ValueError(
                    f"task {task.name!r} run {run_id!r} references undeclared "
                    f"task parameter {name!r}."
                )
            forwarded_parameters.add(name)
        for input_name, link in run.get("inputs", {}).items():
            file_input = declared_inputs.get(input_name)
            if file_input is None:
                raise ValueError(
                    f"task {task.name!r} run {run_id!r} has no input "
                    f"{input_name!r}."
                )
            if not isinstance(link, Mapping) or set(link) != {"run_id", "output"}:
                raise TypeError(
                    f"task {task.name!r} run {run_id!r} input {input_name!r} "
                    "must specify run_id and output."
                )
            producer_id = link["run_id"]
            output_name = link["output"]
            if not is_valid_runnable_name(producer_id):
                raise ValueError(
                    f"task {task.name!r} run {run_id!r} input {input_name!r} "
                    "run_id must be a valid name."
                )
            if type(output_name) is not str or not output_name.strip():
                raise ValueError(
                    f"task {task.name!r} run {run_id!r} input {input_name!r} "
                    "output must be non-blank."
                )
            producer = by_id.get(producer_id)
            if producer is None:
                raise ValueError(
                    f"task {task.name!r} run {run_id!r} input "
                    f"{input_name!r} references unknown run {producer_id!r}."
                )
            try:
                output = producer["step"].spec.output(output_name)
            except KeyError as error:
                raise ValueError(
                    f"task {task.name!r} run {run_id!r} input "
                    f"{input_name!r} references unknown output "
                    f"{output_name!r} on run {producer_id!r}."
                ) from error
            if not file_input.accepts_output(output):
                raise ValueError(
                    f"task {task.name!r} run {run_id!r} input "
                    f"{input_name!r} cannot accept output {output_name!r} "
                    f"from run {producer_id!r}."
                )
    unused_parameters = declared_parameters - forwarded_parameters
    if unused_parameters:
        names = ", ".join(sorted(unused_parameters))
        raise ValueError(f"task {task.name!r} has unused parameter(s): {names}.")
    return tuple(runs)
