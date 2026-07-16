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

from ASOkai._cwl.publisher import PUBLISHED_DIR, PublicationEntry, PublicationPlan
from ASOkai._cwl.spec import (
    BaseCwlGenerator,
    StepCwlGenerator,
    step_cwl_filename,
    step_cwl_run_path,
)
from ASOkai._pipeline.base import Step
from ASOkai._pipeline.registry import get_steps


def _cwl_step_id(step_name: str) -> str:
    """Return a CWL-safe step id for a registry step name."""
    return f"step_{step_name.replace('-', '_')}"


def _output_names(step: Step) -> tuple[str, ...]:
    """Return CWL output names from the step specification."""
    return step.spec.output_names()


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


def _validate_unique_temp_filenames(step_objs: list[Step]) -> None:
    """Reject output files that would collide inside CWL working directories."""
    owners: dict[str, str] = {}
    for step in step_objs:
        for output in step.spec.outputs:
            owner = f"{step.name}/{output.name}"
            previous = owners.get(output.temp_filename)
            if previous is not None:
                raise ValueError(
                    f"CWL temporary filename '{output.temp_filename}' is used by both "
                    f"'{previous}' and '{owner}'."
                )
            owners[output.temp_filename] = owner


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
        pre_resolved: dict[str, Path],
        config: dict,
        publication_plan: PublicationPlan,
    ) -> dict[str, Any]:
        """
        Build a CWL Workflow-class job document that wires together the given steps.

        Wire-up rules:
        - pre_resolved keys become top-level ``File`` inputs.
        - input_overrides not covered by an in-sequence dependency become top-level
          inputs matching the declared step CWL type.
        - config_map values become top-level inputs matching declared step CWL types.
        - every planned step output is wired into the final publisher.
        - the publisher's top-level data roots become workflow outputs.
        """
        step_by_name = {s.name: s for s in step_objs}
        step_names_in_seq = set(step_by_name)
        all_inputs: dict[str, Any] = {}
        declared_step_inputs = {
            input_name
            for step in step_objs
            for input_name in step.cwl_spec.input_names()
        }

        for key in pre_resolved:
            if key in declared_step_inputs:
                _declare_workflow_input(all_inputs, key, "File")

        for step in step_objs:
            input_types = step.cwl_spec.input_types()
            for cwl_key in step.input_overrides:
                wired_by_dependency = any(
                    dep_name in step_names_in_seq
                    and cwl_key in _output_names(step_by_name[dep_name])
                    for dep_name in step.dependencies
                )
                if not wired_by_dependency:
                    _declare_workflow_input(all_inputs, cwl_key, input_types[cwl_key])

        for step in step_objs:
            input_types = step.cwl_spec.input_types()
            for cwl_key in step.config_map:
                _declare_workflow_input(all_inputs, cwl_key, input_types[cwl_key])

        cwl_steps = {}
        for step in step_objs:
            in_map: dict[str, str | dict] = {}

            for cwl_key in step.config_map:
                in_map[cwl_key] = cwl_key

            for cwl_key in step.input_overrides:
                if cwl_key not in in_map:
                    in_map[cwl_key] = cwl_key

            consumer_inputs = step.cwl_spec.input_names()
            for dep_name in step.dependencies:
                if dep_name not in step_names_in_seq:
                    dep_step = step_by_name.get(dep_name) or get_steps().get(dep_name)
                    if dep_step is None:
                        continue
                    for out_key in _output_names(dep_step):
                        if out_key in pre_resolved and out_key in consumer_inputs:
                            in_map[out_key] = out_key
                    continue

                dep_step = step_by_name[dep_name]
                dep_cwl_id = _cwl_step_id(dep_name)
                for out_key in _output_names(dep_step):
                    if out_key not in consumer_inputs:
                        continue
                    if out_key in pre_resolved:
                        in_map[out_key] = out_key
                    else:
                        in_map[out_key] = f"{dep_cwl_id}/{out_key}"

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
        pre_resolved: dict[str, Path],
        config: dict,
        publication_plan: PublicationPlan,
    ) -> str:
        return self.dump(
            self.document(
                step_objs,
                pre_resolved,
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
    pre_resolved: dict[str, Path],
    config: dict,
) -> GeneratedCwlBundle:
    """Generate every CWL document required by a runnable bundle."""
    _validate_unique_temp_filenames(step_objs)
    publication_plan = build_publication_plan(step_objs, config)
    run_cwl = JobCwlGenerator().render(
        step_objs,
        pre_resolved,
        config,
        publication_plan,
    )
    step_generator = StepCwlGenerator()
    return GeneratedCwlBundle(
        run_cwl=run_cwl,
        publish_cwl=PublisherCwlGenerator().render(publication_plan),
        output_layout=publication_plan.render(),
        step_cwls={
            step_cwl_filename(step): step_generator.render(step)
            for step in step_objs
        },
    )
