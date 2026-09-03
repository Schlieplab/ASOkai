#!/usr/bin/env python
"""
Filename: src/ASOkai/_cwl/generation.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Generate top-level runtime CWL documents from ASOkai pipeline steps.
License: LGPL-3.0-or-later
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import re
from typing import Any

import yaml

from ASOkai._cwl.input_resolution import (
    workflow_file_input_id,
    workflow_input_id,
)
from ASOkai._cwl.publisher import PUBLISHED_DIR, PublicationEntry, PublicationPlan
from ASOkai._cwl.resources import cwl_resource_requirement
from ASOkai._pipeline import config as cfg
from ASOkai._pipeline.contracts.execution import StepRun, StepRunOutput
from ASOkai._pipeline.contracts.files import FileInput
from ASOkai._pipeline.steps.base import Step


class BaseCwlGenerator:
    """Shared YAML rendering behavior for generated CWL documents."""

    cwl_version = "v1.2"

    def dump(self, doc: dict[str, Any]) -> str:
        return yaml.safe_dump(doc, default_flow_style=False, sort_keys=False)


class StepCwlGenerator(BaseCwlGenerator):
    """Render a step's generated spec as a CWL CommandLineTool document."""

    def document(
        self,
        run: StepRun,
        *,
        resource_requirement: dict[str, int] | None = None,
    ) -> dict[str, Any]:
        step = run.step
        spec = run.cwl_spec()
        doc: dict[str, Any] = {
            "cwlVersion": self.cwl_version,
            "class": "CommandLineTool",
            "baseCommand": spec.command_for_step(step.name),
            "doc": step.description,
        }
        requirements = deepcopy(spec.requirements)
        if resource_requirement:
            authored_resources = requirements.get("ResourceRequirement", {})
            requirements["ResourceRequirement"] = {
                **authored_resources,
                **resource_requirement,
            }
        if requirements:
            doc["requirements"] = requirements
        if spec.arguments:
            doc["arguments"] = [argument.to_cwl() for argument in spec.arguments]
        doc["inputs"] = {item.name: item.to_cwl() for item in spec.inputs}
        doc["outputs"] = {item.name: item.to_cwl() for item in spec.outputs}
        doc.update(deepcopy(spec.extra))
        return doc

    def render(
        self,
        run: StepRun,
        *,
        shebang: bool = True,
        resource_requirement: dict[str, int] | None = None,
    ) -> str:
        text = self.dump(
            self.document(
                run,
                resource_requirement=resource_requirement,
            )
        )
        if shebang:
            return f"#!/usr/bin/env cwl-runner\n{text}"
        return text


def step_cwl_filename(run: StepRun) -> str:
    """Return the generated CommandLineTool filename for one concrete run."""
    return f"{run.run_id}.cwl"


def step_cwl_run_path(run: StepRun) -> str:
    """Return the relative run path used inside generated jobs."""
    return f"steps/{step_cwl_filename(run)}"


def _cwl_step_id(step_name: str) -> str:
    """Return a CWL-safe step id for a registry step name."""
    return f"step_{step_name.replace('-', '_')}"


def _validate_planned_runs(runs: list[StepRun]) -> None:
    """Reject conflicting run definitions in one generated workflow."""
    by_id: dict[str, StepRun] = {}
    for run in runs:
        if run.run_id in by_id:
            raise ValueError(f"Duplicate planned run id: {run.run_id!r}.")
        by_id[run.run_id] = run

    for run in runs:
        for binding in run.inputs:
            source = binding.source
            if not isinstance(source, StepRunOutput):
                continue
            producer = source.run
            planned_producer = by_id.get(producer.run_id)
            if planned_producer is not None and planned_producer is not producer:
                raise ValueError(
                    f"Run '{run.run_id}' input '{binding.file_input.name}' "
                    "references a different StepRun object for planned run "
                    f"'{producer.run_id}'."
                )


def _publisher_output_ids(plan: PublicationPlan) -> dict[str, str]:
    """Return stable CWL output ids for publication roots."""
    result: dict[str, str] = {}
    used: set[str] = set()
    for index, root in enumerate(plan.roots, start=1):
        normalized = re.sub(r"[^A-Za-z0-9_]", "_", root)
        base = f"published_{normalized}" if normalized else f"published_{index}"
        candidate = base
        suffix = 2
        while candidate in used:
            candidate = f"{base}_{suffix}"
            suffix += 1
        used.add(candidate)
        result[root] = candidate
    return result


def build_publication_plan(runs: list[StepRun]) -> PublicationPlan:
    """Resolve every planned output to a path relative to ``datadir``."""
    entries: list[PublicationEntry] = []
    for run in runs:
        output_paths = run.output_paths()
        datadir = Path(run.config["datadir"])
        for output in run.step.spec.outputs:
            relative = output_paths[output.name].relative_to(datadir)
            entries.append(
                PublicationEntry(
                    run.output(output).qualified_name,
                    PurePosixPath(*relative.parts),
                )
            )
    return PublicationPlan(tuple(entries))


def _publication_sources(runs: list[StepRun]) -> list[str]:
    """Return step output sources in publication-manifest order."""
    return [
        f"{_cwl_step_id(run.run_id)}/{output.name}"
        for run in runs
        for output in run.step.spec.outputs
    ]


def _workflow_input_type(cwl_type: Any) -> Any:
    """Return a valid Workflow input declaration for a step input type."""
    if isinstance(cwl_type, dict):
        return {"type": cwl_type}
    return cwl_type


def _declare_workflow_input(
    all_inputs: dict[str, Any],
    name: str,
    cwl_type: Any,
) -> None:
    """Declare one run-qualified workflow input."""
    cwl_type = _workflow_input_type(cwl_type)
    if name in all_inputs and all_inputs[name] != cwl_type:
        raise ValueError(
            f"Workflow input '{name}' is declared with conflicting CWL types. "
            "A concrete run cannot declare one input with multiple types."
        )
    all_inputs.setdefault(name, deepcopy(cwl_type))


class JobCwlGenerator(BaseCwlGenerator):
    """Build the top-level runtime CWL document that wires together planned steps."""

    def document(
        self,
        runs: list[StepRun],
        publication_plan: PublicationPlan,
    ) -> dict[str, Any]:
        """
        Build a CWL Workflow-class job document that wires together the given steps.

        Wire-up rules:
        - producer outputs outside the plan become top-level ``File`` inputs.
        - input overrides become top-level inputs matching the declared step
          CWL type.
        - config_map values become top-level inputs matching declared step CWL types.
        - every planned step output is wired into the final publisher.
        - the publisher's top-level data roots become workflow outputs.
        """
        _validate_planned_runs(runs)
        runs_to_execute = set(runs)
        all_inputs: dict[str, Any] = {}
        for run in runs:
            input_types = run.cwl_spec().input_types()
            for binding in run.inputs:
                file_input = binding.file_input
                source = binding.source
                if (
                    not isinstance(source, StepRunOutput)
                    or source.run not in runs_to_execute
                ):
                    _declare_workflow_input(
                        all_inputs,
                        workflow_file_input_id(
                            run,
                            file_input.name,
                            source,
                        ),
                        input_types[file_input.name],
                    )

        for run in runs:
            step = run.step
            input_types = run.cwl_spec().input_types()
            for cwl_key in step.config_map:
                _declare_workflow_input(
                    all_inputs,
                    workflow_input_id(run, cwl_key),
                    input_types[cwl_key],
                )

        cwl_steps = {}
        for run in runs:
            step = run.step
            config = dict(run.config)
            in_map: dict[str, str | dict] = {}

            if step.supports_multiple_processes:
                in_map[cfg.RESOURCE_N_PROCESSES_KEY] = {
                    "default": cfg.step_resources(config, step)[
                        cfg.RESOURCE_N_PROCESSES_KEY
                    ]
                }

            for cwl_key in step.config_map:
                in_map[cwl_key] = workflow_input_id(run, cwl_key)

            for binding in run.inputs:
                file_input = binding.file_input
                source = binding.source
                if (
                    not isinstance(source, StepRunOutput)
                    or source.run not in runs_to_execute
                ):
                    in_map[file_input.name] = workflow_file_input_id(
                        run,
                        file_input.name,
                        source,
                    )
                else:
                    in_map[file_input.name] = (
                        f"{_cwl_step_id(source.run.run_id)}/{source.output.name}"
                    )

            cwl_steps[_cwl_step_id(run.run_id)] = {
                "run": step_cwl_run_path(run),
                "in": in_map,
                "out": [output.name for output in step.spec.outputs],
            }

        publisher_outputs = _publisher_output_ids(publication_plan)
        cwl_steps["publish_outputs"] = {
            "run": "publish.cwl",
            "in": {
                "files": {
                    "source": _publication_sources(runs),
                    "linkMerge": "merge_flattened",
                },
            },
            "out": list(publisher_outputs.values()),
        }

        cwl_outputs = {
            output_id: {
                "type": "File" if _root_is_file(publication_plan, root) else "Directory",
                "outputSource": f"publish_outputs/{output_id}",
            }
            for root, output_id in publisher_outputs.items()
        }

        return {
            "cwlVersion": self.cwl_version,
            "class": "Workflow",
            "requirements": {"MultipleInputFeatureRequirement": {}},
            "inputs": all_inputs,
            "steps": cwl_steps,
            "outputs": cwl_outputs,
        }

    def render(
        self,
        runs: list[StepRun],
        publication_plan: PublicationPlan,
    ) -> str:
        return self.dump(
            self.document(
                runs,
                publication_plan,
            )
        )


def _root_is_file(plan: PublicationPlan, root: str) -> bool:
    """Return whether a publication root is itself a single file."""
    matching = [entry for entry in plan.entries if entry.destination.parts[0] == root]
    return len(matching) == 1 and len(matching[0].destination.parts) == 1


class PublisherCwlGenerator(BaseCwlGenerator):
    """Generate the final CommandLineTool that publishes all workflow outputs."""

    def document(self, plan: PublicationPlan) -> dict[str, Any]:
        output_ids = _publisher_output_ids(plan)
        outputs = {}
        for root, output_id in output_ids.items():
            outputs[output_id] = {
                "type": "File" if _root_is_file(plan, root) else "Directory",
                "outputBinding": {"glob": f"{PUBLISHED_DIR}/{root}"},
            }

        return {
            "cwlVersion": self.cwl_version,
            "class": "CommandLineTool",
            "baseCommand": ["ASOkai", "publish-outputs"],
            "doc": "Publish all planned outputs into their data-directory hierarchy.",
            "inputs": {
                "manifest": {
                    "type": "File",
                    "default": {
                        "class": "File",
                        "location": "output-layout.yml",
                    },
                    "inputBinding": {"position": 1},
                },
                "files": {
                    "type": {"type": "array", "items": "File"},
                    "inputBinding": {"position": 2},
                },
            },
            "outputs": outputs,
        }

    def render(self, plan: PublicationPlan, *, shebang: bool = True) -> str:
        text = self.dump(self.document(plan))
        if shebang:
            return f"#!/usr/bin/env cwl-runner\n{text}"
        return text


@dataclass(frozen=True)
class GeneratedCwlBundle:
    """Complete generated document set for one runnable CWL bundle."""

    run_cwl: str
    publish_cwl: str
    output_layout: str
    step_cwls: dict[str, str]


def generate_cwl_bundle(
    runs: list[StepRun],
) -> GeneratedCwlBundle:
    """Generate every CWL document required by a runnable bundle."""
    publication_plan = build_publication_plan(runs)
    run_cwl = JobCwlGenerator().render(
        runs,
        publication_plan,
    )
    step_generator = StepCwlGenerator()
    step_cwls = {}
    for run in runs:
        step = run.step
        config = dict(run.config)
        authored_requirement = run.cwl_spec().requirements.get(
            "ResourceRequirement",
            {},
        )
        resource_requirement = cwl_resource_requirement(
            config,
            step,
            authored_requirement,
        )
        step_cwls[step_cwl_filename(run)] = step_generator.render(
            run,
            resource_requirement=resource_requirement,
        )

    return GeneratedCwlBundle(
        run_cwl=run_cwl,
        publish_cwl=PublisherCwlGenerator().render(publication_plan),
        output_layout=publication_plan.render(),
        step_cwls=step_cwls,
    )
