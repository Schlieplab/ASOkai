#!/usr/bin/env python
"""
Filename: src/ASOkai/_pipeline/tasks/base.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Contracts for named collections of pipeline step runs.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

from typing import Mapping, Protocol, Sequence, runtime_checkable

from ASOkai._pipeline.base import Runnable, is_valid_runnable_name
from ASOkai._pipeline.contracts.run_spec import RunSpec
from ASOkai._pipeline.steps.base import Step


@runtime_checkable
class Task(Runnable, Protocol):
    """Named step collection, optionally declared as named runs."""

    @property
    def steps(self) -> Sequence[Step]:
        """Expose declared runs to existing catalog and description APIs."""
        return tuple(run.step for run in getattr(self, "runs", ()))


def validate_task_parameter_contract(task: Task) -> None:
    """Reject the removed task parameter declaration API."""
    if getattr(task, "params", ()):
        raise ValueError(
            "task params declarations are no longer supported; "
            "use matching child step parameter names in task selections."
        )


def validate_task_runs(task: Task) -> tuple[RunSpec, ...]:
    """Validate one task's local run names, ports, and links."""
    runs = getattr(task, "runs", None)
    if isinstance(runs, (str, bytes)) or not isinstance(runs, Sequence) or not runs:
        raise TypeError("task runs must be a non-empty sequence.")

    by_id: dict[str, RunSpec] = {}
    for run in runs:
        if not isinstance(run, RunSpec):
            raise TypeError("task runs must contain only RunSpec values.")
        run_id = run.run_id
        if not is_valid_runnable_name(run_id):
            raise ValueError(f"task {task.name!r} run id must be a local name.")
        if run_id in by_id:
            raise ValueError(f"task {task.name!r} has duplicate run id {run_id!r}.")
        by_id[run_id] = run

    for run in runs:
        run_id = run.run_id
        step = run.step
        declared_inputs = {item.name: item for item in step.spec.inputs}
        run_parameters = run.parameters
        unknown_parameters = set(run_parameters) - {
            parameter.name for parameter in step.spec.params
        }
        if unknown_parameters:
            names = ", ".join(sorted(str(name) for name in unknown_parameters))
            raise ValueError(
                f"task {task.name!r} run {run_id!r} has unknown "
                f"parameter(s): {names}."
            )
        for parameter in step.spec.params:
            if parameter.name in run_parameters:
                parameter.validate(run_parameters[parameter.name])
        for input_name, link in run.inputs.items():
            file_input = declared_inputs.get(input_name)
            if file_input is None:
                raise ValueError(
                    f"task {task.name!r} run {run_id!r} has no input "
                    f"{input_name!r}."
                )
            if not isinstance(link, Mapping) or set(link) != {"from_run", "output"}:
                raise TypeError(
                    f"task {task.name!r} run {run_id!r} input {input_name!r} "
                    "must specify from_run and output."
                )
            producer_id = link["from_run"]
            output_name = link["output"]
            if not is_valid_runnable_name(producer_id):
                raise ValueError(
                    f"task {task.name!r} run {run_id!r} input {input_name!r} "
                    "from_run must be a valid name."
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
                output = producer.step.spec.output(output_name)
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
    return tuple(runs)
