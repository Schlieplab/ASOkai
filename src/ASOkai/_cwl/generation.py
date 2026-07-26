#!/usr/bin/env python
"""
Filename: src/ASOkai/_cwl/generation.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Version: 0.1.1
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

from ASOkai._cwl.publisher import PUBLISHED_DIR, PublicationEntry, PublicationPlan
from ASOkai._cwl.resources import cwl_resource_requirement
from ASOkai._pipeline import config as cfg
from ASOkai._pipeline.files import FileInput
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
        step,
        config: dict,
        *,
        resource_requirement: dict[str, int] | None = None,
    ) -> dict[str, Any]:
        spec = step.cwl_spec(config)
        doc: dict[str, Any] = {
            "cwlVersion": self.cwl_version,
            "class": "CommandLineTool",
            "baseCommand": spec.command_for_step(step.name),
            "doc": spec.doc_for_step(step.description),
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
        step,
        config: dict,
        *,
        shebang: bool = True,
        resource_requirement: dict[str, int] | None = None,
    ) -> str:
        text = self.dump(
            self.document(
                step,
                config,
                resource_requirement=resource_requirement,
            )
        )
        if shebang:
            return f"#!/usr/bin/env cwl-runner\n{text}"
        return text


def step_cwl_filename(step) -> str:
    """Return the generated CommandLineTool filename for a step."""
    return f"{step.name}.cwl"


def step_cwl_run_path(step) -> str:
    """Return the relative run path used inside generated jobs."""
    return f"steps/{step_cwl_filename(step)}"


def _cwl_step_id(step_name: str) -> str:
    """Return a CWL-safe step id for a registry step name."""
    return f"step_{step_name.replace('-', '_')}"


def _output_names(step: Step) -> tuple[str, ...]:
    """Return CWL output names from the step specification."""
    return step.spec.output_names()


def _validate_planned_connections(step_objs: list[Step]) -> None:
    """Validate direct output identities before rendering workflow wiring."""
    by_name: dict[str, Step] = {}
    for step in step_objs:
        if step.name in by_name:
            raise ValueError(f"Duplicate planned step name: {step.name!r}.")
        by_name[step.name] = step

    for step in step_objs:
        for file_input in step.spec.inputs:
            source = file_input.source
            producer = by_name.get(source.producer)
            if producer is None:
                continue
            try:
                declared = producer.spec.output(source.name)
            except KeyError as error:
                raise ValueError(
                    f"Step '{step.name}' input '{file_input.name}' references "
                    f"unknown output '{source.name}' on step '{source.producer}'."
                ) from error
            if declared is not source:
                raise ValueError(
                    f"Step '{step.name}' input '{file_input.name}' references "
                    f"an output declaration that does not belong to "
                    f"'{source.producer}'."
                )


def _workflow_output_id(step: Step, output_name: str) -> str:
    """Return a unique top-level output id for one step output."""
    return f"{_cwl_step_id(step.name)}__{output_name}"


def _publisher_output_ids(plan: PublicationPlan) -> dict[str, str]:
    """Return stable CWL output ids for publication roots."""
    result: dict[str, str] = {}
    used: set[str] = set()
    for index, root in enumerate(plan.roots, start=1):
        normalized = re.sub(r"[^A-Za-z0-9_]", "_", root)
        candidate = f"published_{normalized}" if normalized else f"published_{index}"
        if candidate in used:
            candidate = f"{candidate}_{index}"
        used.add(candidate)
        result[root] = candidate
    return result


def build_publication_plan(step_objs: list[Step], config: dict) -> PublicationPlan:
    """Resolve every planned output to a path relative to ``datadir``."""
    entries: list[PublicationEntry] = []
    for step in step_objs:
        step.validated_output_paths(config)
        for output in step.spec.outputs:
            relative = step.output_relative_path(output.name, config)
            entries.append(
                PublicationEntry(
                    _workflow_output_id(step, output.name),
                    PurePosixPath(*relative.parts),
                )
            )
    if not entries:
        raise ValueError("A generated CWL job must publish at least one output.")
    return PublicationPlan(tuple(entries))


def _publication_sources(step_objs: list[Step]) -> list[str]:
    """Return step output sources in publication-manifest order."""
    return [
        f"{_cwl_step_id(step.name)}/{output.name}"
        for step in step_objs
        for output in step.spec.outputs
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
    """Declare a shared workflow input, rejecting incompatible reuse."""
    cwl_type = _workflow_input_type(cwl_type)
    if name in all_inputs and all_inputs[name] != cwl_type:
        raise ValueError(
            f"Workflow input '{name}' is declared with conflicting CWL types. "
            "Use distinct parameter names for unrelated step inputs."
        )
    all_inputs.setdefault(name, deepcopy(cwl_type))


class JobCwlGenerator(BaseCwlGenerator):
    """Build the top-level runtime CWL document that wires together planned steps."""

    def document(
        self,
        step_objs: list[Step],
        config: dict,
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
        _validate_planned_connections(step_objs)
        step_names_in_seq = {step.name for step in step_objs}
        all_inputs: dict[str, Any] = {}
        for step in step_objs:
            input_types = step.cwl_spec(config).input_types()
            for file_input in step.spec.inputs:
                if (
                    file_input.configured_override_path(config) is not None
                    or file_input.source.producer not in step_names_in_seq
                ):
                    _declare_workflow_input(
                        all_inputs,
                        file_input.name,
                        input_types[file_input.name],
                    )

        for step in step_objs:
            input_types = step.cwl_spec(config).input_types()
            for cwl_key in step.config_map:
                _declare_workflow_input(all_inputs, cwl_key, input_types[cwl_key])

        cwl_steps = {}
        for step in step_objs:
            in_map: dict[str, str | dict] = {}

            in_map[cfg.RESOURCE_N_PROCESSES_KEY] = {
                "default": cfg.step_resources(config, step.name)[
                    cfg.RESOURCE_N_PROCESSES_KEY
                ]
            }

            for cwl_key in step.config_map:
                in_map[cwl_key] = cwl_key

            for file_input in step.spec.inputs:
                source = file_input.source
                if (
                    file_input.configured_override_path(config) is not None
                    or source.producer not in step_names_in_seq
                ):
                    in_map[file_input.name] = file_input.name
                else:
                    in_map[file_input.name] = (
                        f"{_cwl_step_id(source.producer)}/{source.name}"
                    )

            cwl_steps[_cwl_step_id(step.name)] = {
                "run": step_cwl_run_path(step),
                "in": in_map,
                "out": list(_output_names(step)),
            }

        publisher_outputs = _publisher_output_ids(publication_plan)
        cwl_steps["publish_outputs"] = {
            "run": "publish.cwl",
            "in": {
                "files": {
                    "source": _publication_sources(step_objs),
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
        step_objs: list[Step],
        config: dict,
        publication_plan: PublicationPlan,
    ) -> str:
        return self.dump(
            self.document(
                step_objs,
                config,
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
    step_objs: list[Step],
    config: dict,
) -> GeneratedCwlBundle:
    """Generate every CWL document required by a runnable bundle."""
    publication_plan = build_publication_plan(step_objs, config)
    run_cwl = JobCwlGenerator().render(
        step_objs,
        config,
        publication_plan,
    )
    step_generator = StepCwlGenerator()
    step_cwls = {}
    for step in step_objs:
        authored_requirement = step.cwl_spec(config).requirements.get(
            "ResourceRequirement",
            {},
        )
        resource_requirement = cwl_resource_requirement(
            config,
            step.name,
            authored_requirement,
        )
        step_cwls[step_cwl_filename(step)] = step_generator.render(
            step,
            config,
            resource_requirement=resource_requirement,
        )

    return GeneratedCwlBundle(
        run_cwl=run_cwl,
        publish_cwl=PublisherCwlGenerator().render(publication_plan),
        output_layout=publication_plan.render(),
        step_cwls=step_cwls,
    )
