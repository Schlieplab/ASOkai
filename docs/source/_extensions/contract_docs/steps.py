#!/usr/bin/env python
"""
Filename: docs/source/_extensions/contract_docs/steps.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Version: 0.1.1
Description: Generated references for built-in pipeline steps.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, cast, get_origin

import yaml
from docutils import nodes
from docutils.parsers.rst import directives
from sphinx.util.docutils import SphinxDirective

from .configuration import (
    collect_step_config_fields,
    collect_step_schema_rules,
    config_table,
    get_built_in_step,
    get_built_in_steps,
    load_packaged_config_schema,
    rules_section,
)
from .rendering import (
    details,
    document_link,
    documented_items,
    documented_section,
    section,
    table,
)

PROJECT_ROOT = Path(__file__).parents[4]
EXAMPLE_CONFIG_PATH = PROJECT_ROOT / "examples/config.example.yaml"


def _file_type_label(file_type: Any) -> str:
    from ASOkai._pipeline.contracts.file_types import JsonFile
    from ASOkai._pipeline.contracts.json_schema import json_file_type_name

    if isinstance(file_type, JsonFile) and file_type.value_type is not None:
        return f"JSON — {json_file_type_name(file_type.value_type)}"
    return file_type.format_name


def _file_type_reference(
    file_type: Any,
    *,
    refdoc: str,
) -> nodes.inline:
    """Render a file format, linking JSON values to their owning classes."""
    from ASOkai._pipeline.contracts.file_types import JsonFile

    from .file_contracts import class_contract_link, json_contract_types

    result = nodes.inline()
    if isinstance(file_type, JsonFile):
        links = [
            class_contract_link(serializable_type, refdoc=refdoc)
            for serializable_type in json_contract_types(file_type)
        ]
    else:
        links = []

    if links:
        result += nodes.Text("JSON — ")
        if get_origin(file_type.value_type) is list:
            result += nodes.Text("list[")
        for index, link in enumerate(links):
            if index:
                result += nodes.Text(" or ")
            result += link
        if get_origin(file_type.value_type) is list:
            result += nodes.Text("]")
        return result

    result += nodes.Text(_file_type_label(file_type))
    return result


def _inputs_table(
    file_inputs: list[Any] | tuple[Any, ...],
    *,
    refdoc: str,
) -> nodes.table:
    rows = []
    for file_input in file_inputs:
        source_name = f"{file_input.source.producer}.{file_input.source.name}"
        input_details: list[tuple[str, str | nodes.Node, bool]] = [
            ("Source", source_name, True)
        ]
        if file_input.override is not None:
            input_details.append(("Override", file_input.override, True))
        input_details.extend(
            (
                (
                    "Format",
                    _file_type_reference(
                        file_input.file_type,
                        refdoc=refdoc,
                    ),
                    False,
                ),
                ("Description", file_input.doc or "—", False),
            )
        )
        rows.append(
            (
                (file_input.name, True),
                details(input_details),
            )
        )
    return table(
        ("File input", "Details"),
        rows,
        (25, 75),
        css_class="asokai-step-inputs",
    )


def _load_example_config() -> dict[str, Any]:
    config = yaml.safe_load(EXAMPLE_CONFIG_PATH.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError(f"{EXAMPLE_CONFIG_PATH} must contain a mapping.")
    return config


def _scalar_outputs_table() -> nodes.table:
    return table(
        ("Scalar output", "Details"),
        [
            (
                ("None", False),
                ("This step does not produce scalar outputs.", False),
            )
        ],
        (30, 70),
        css_class="asokai-step-scalar-outputs",
    )


def _file_outputs_table(
    step: Any,
    example_config: Mapping[str, Any],
    *,
    refdoc: str,
) -> nodes.table:
    rows = []
    for output in step.spec.outputs:
        try:
            example_path = str(
                step.output_relative_path(output.name, dict(example_config))
            )
        except (KeyError, TypeError, ValueError):
            example_path = "—"
        rows.append(
            (
                (output.name, True),
                details(
                    (
                        (
                            "Format",
                            _file_type_reference(
                                output.file_type,
                                refdoc=refdoc,
                            ),
                            False,
                        ),
                        ("Description", output.doc or "—", False),
                        ("Path template", output.destination.template, True),
                        ("Example path", example_path, True),
                    )
                ),
            )
        )
    return table(
        ("File output", "Details"),
        rows,
        (25, 75),
        css_class="asokai-step-file-outputs",
    )


def _resources_table(step: Any, config_fields: list[Any]) -> nodes.table:
    """Show each resource once, together with its resolution order."""
    from ASOkai._pipeline.config import (
        DEFAULT_STEP_RESOURCES,
        RESOURCE_N_PROCESSES_KEY,
        step_resource_names,
    )

    fields_by_path = {field.path: field for field in config_fields}
    configurable_resources = set(step_resource_names(step))
    rows = []
    for resource_name, fallback in DEFAULT_STEP_RESOURCES.items():
        if resource_name not in configurable_resources:
            if resource_name == RESOURCE_N_PROCESSES_KEY:
                rows.append(
                    (
                        (resource_name, True),
                        details(
                            (
                                ("Fixed value", str(fallback), False),
                                (
                                    "Description",
                                    "This step always runs with one process.",
                                    False,
                                ),
                            )
                        ),
                    )
                )
            continue
        default_field = fields_by_path[f"resources.default.{resource_name}"]
        step_field = fields_by_path[f"resources.{step.name}.{resource_name}"]
        accepted_value = step_field.value_type
        if step_field.constraints != "—":
            accepted_value += f"; {step_field.constraints}"
        rows.append(
            (
                (resource_name, True),
                details(
                    (
                        ("Step override", step_field.path, True),
                        ("Shared default", default_field.path, True),
                        ("Built-in fallback", str(fallback), False),
                        ("Accepted value", accepted_value, False),
                        ("Description", step_field.description, False),
                    )
                ),
            )
        )
    return table(
        ("Resource setting", "Details"),
        rows,
        (25, 75),
        css_class="asokai-step-resources",
    )


def _step_kind(step: Any) -> str:
    from ASOkai._pipeline.steps.analysis.base import AnalysisStep

    return "Analysis step" if isinstance(step, AnalysisStep) else "Core step"


def build_step_list(
    step_kind: str,
    *,
    include_descriptions: bool = False,
    refdoc: str = "",
) -> nodes.bullet_list:
    """Build a linked list of registered built-in steps of one kind."""
    from ASOkai._pipeline.steps.analysis.base import AnalysisStep
    from ASOkai._pipeline.steps.core.base import CoreStep

    step_types = {
        "analysis": AnalysisStep,
        "core": CoreStep,
    }
    try:
        step_type = step_types[step_kind]
    except KeyError as error:
        expected = ", ".join(step_types)
        raise ValueError(
            f"Unknown step kind {step_kind!r}; expected one of: {expected}."
        ) from error

    step_list = nodes.bullet_list()
    for step in get_built_in_steps():
        if not isinstance(step, step_type):
            continue
        item = nodes.list_item()
        paragraph = nodes.paragraph()
        paragraph += document_link(
            f"steps/{step.name}",
            step.name,
            refdoc=refdoc,
        )
        if include_descriptions:
            paragraph += nodes.Text(f" — {step.description}")
        item += paragraph
        step_list += item
    return step_list


def _dependency_section(step: Any, *, refdoc: str) -> nodes.section:
    if not step.spec.inputs:
        return section(
            "Dependencies",
            [nodes.paragraph(text="This step has no step dependencies.")],
        )

    grouped: dict[str, list[Any]] = {}
    for file_input in step.spec.inputs:
        grouped.setdefault(file_input.source.producer, []).append(file_input)

    dependency_list = nodes.bullet_list()
    for producer, inputs in grouped.items():
        item = nodes.list_item()
        paragraph = nodes.paragraph()
        paragraph += document_link(
            f"steps/{producer}",
            producer,
            refdoc=refdoc,
        )
        override_paths = [
            file_input.override
            for file_input in inputs
            if file_input.override is not None
        ]
        if override_paths:
            if len(inputs) == 1:
                paragraph += nodes.Text(" is required unless ")
                paragraph += nodes.literal(override_paths[0], override_paths[0])
                paragraph += nodes.Text(" is configured.")
            else:
                paragraph += nodes.Text(
                    " is required unless every input from it is replaced."
                )
                overrides = nodes.bullet_list()
                for path in override_paths:
                    override_item = nodes.list_item()
                    override_paragraph = nodes.paragraph()
                    override_paragraph += nodes.literal(path, path)
                    override_item += override_paragraph
                    overrides += override_item
                item += paragraph
                item += nodes.paragraph(text="Override all of:")
                item += overrides
                dependency_list += item
                continue
        else:
            paragraph += nodes.Text(" is always required.")
        item += paragraph
        dependency_list += item
    return section("Dependencies", [dependency_list])


def _transitive_steps(step: Any) -> list[Any]:
    """Return dependencies followed by the selected step."""
    from ASOkai.Plugins._registry import _BUILTIN_STEPS

    registry = {candidate.name: candidate for candidate in _BUILTIN_STEPS}
    ordered: list[Any] = []
    visited: set[str] = set()

    def visit(candidate: Any) -> None:
        if candidate.name in visited:
            return
        visited.add(candidate.name)
        for dependency in candidate.spec.dependencies():
            if dependency in registry:
                visit(registry[dependency])
        ordered.append(candidate)

    visit(step)
    return ordered


def _resolve_optional(config: Mapping[str, Any], dotted_path: str) -> Any:
    value: Any = config
    for part in dotted_path.split("."):
        if not isinstance(value, Mapping) or part not in value:
            return None
        value = value[part]
    return value


def _assign_path(config: dict[str, Any], dotted_path: str, value: Any) -> None:
    target = config
    parts = dotted_path.split(".")
    for part in parts[:-1]:
        nested = target.setdefault(part, {})
        if not isinstance(nested, dict):
            raise TypeError(f"Cannot build example config path {dotted_path!r}.")
        target = nested
    target[parts[-1]] = value


def _example_step_config(
    step: Any, complete_config: Mapping[str, Any]
) -> dict[str, Any]:
    example: dict[str, Any] = {"datadir": complete_config["datadir"]}
    configured_paths: list[str] = []
    for included_step in _transitive_steps(step):
        configured_paths.extend(
            parameter.config
            for parameter in included_step.spec.params
            if parameter.config is not None
        )
        configured_paths.extend(included_step.spec.compatible_with)
    for path in dict.fromkeys(configured_paths):
        value = _resolve_optional(complete_config, path)
        if value is not None:
            _assign_path(example, path, value)
    return example


def _invocation_section(step: Any, complete_config: Mapping[str, Any]) -> nodes.section:
    has_dependencies = bool(step.spec.dependencies())
    command = f"ASOkai run --steps {step.name} --configfile ./config.yaml"
    if has_dependencies:
        command += " --recursive"
    command_block = nodes.literal_block(command, command)

    explanation = (
        "The recursive flag schedules missing dependencies. Omit it when all "
        "dependency outputs already exist or input overrides are configured."
        if has_dependencies
        else "This step can run directly because it has no step dependencies."
    )
    example_config = cast(
        str,
        yaml.safe_dump(
            _example_step_config(step, complete_config),
            sort_keys=False,
        ),
    )
    example_description = (
        "Example configuration for this step and its recursive dependencies:"
        if has_dependencies
        else "Example configuration for this step:"
    )
    return section(
        "Run this step",
        [
            command_block,
            nodes.paragraph(text=explanation),
            nodes.paragraph(text=example_description),
            nodes.literal_block(example_config, example_config),
        ],
    )


def _applicability_section(step: Any) -> nodes.section | None:
    """Describe the configured values supported by one step."""
    if not step.spec.compatible_with:
        return None

    rows = [
        (
            (path, True),
            (", ".join(str(value) for value in supported_values), True),
        )
        for path, supported_values in step.spec.compatible_with.items()
    ]
    return section(
        "Applicability",
        [
            nodes.paragraph(
                text=(
                    "This step can run only when each configured value is "
                    "listed below. Incompatible selections are rejected "
                    "before execution."
                )
            ),
            table(
                ("Configuration path", "Supported values"),
                rows,
                (40, 60),
                css_class="asokai-step-applicability",
            ),
        ],
    )


def _csv_scalar_type_name(value_type: type) -> str:
    """Return the user-facing name of a supported CSV scalar type."""
    return {
        str: "string",
        int: "integer",
        float: "number",
        bool: "boolean",
    }[value_type]


def _analysis_output_columns_table(
    csv_file: Any,
    descriptions: Mapping[str, str],
) -> nodes.table:
    """Render an analysis CSV's declared index and result columns."""
    rows = []
    for name, value_type in csv_file.index.items():
        rows.append(
            (
                (name, True),
                details(
                    (
                        ("Role", "Index", False),
                        ("Accepted value", _csv_scalar_type_name(value_type), False),
                        (
                            "Meaning",
                            descriptions.get(
                                name,
                                "Identifies the item represented by this row.",
                            ),
                            False,
                        ),
                    )
                ),
            )
        )
    for name, value_type in csv_file.columns.items():
        rows.append(
            (
                (name, True),
                details(
                    (
                        ("Role", "Analysis result", False),
                        ("Accepted value", _csv_scalar_type_name(value_type), False),
                        ("Meaning", descriptions.get(name, "—"), False),
                    )
                ),
            )
        )
    return table(
        ("Output column", "Details"),
        rows,
        (30, 70),
        css_class="asokai-analysis-output-columns",
    )


def _analysis_output_section(
    output: Any,
    descriptions: Mapping[str, str],
    *,
    is_primary: bool,
    include_output_name: bool,
) -> nodes.section:
    """Describe the rows and columns of one analysis CSV output."""
    title = f"{output.name} output columns" if include_output_name else "Output columns"
    output_role = (
        "primary analysis table"
        if is_primary
        else "additional analysis table"
    )
    format_description = nodes.paragraph()
    format_description += nodes.Text("The ")
    format_description += nodes.literal(output.name, output.name)
    format_description += nodes.Text(
        f" output is the {output_role}"
        ". It is UTF-8 and comma-separated. Its first row is a "
        "header containing exactly the columns below, in the declared order."
    )
    row_description = nodes.paragraph()
    row_description += nodes.strong(text="Rows: ")
    row_description += nodes.Text(
        output.doc or "One result for each item processed by the analysis."
    )
    row_description += nodes.Text(
        " Index columns identify the item; analysis-result columns contain "
        "the computed values."
    )
    return section(
        title,
        [
            format_description,
            row_description,
            _analysis_output_columns_table(output.file_type, descriptions),
        ],
    )


def _analysis_section(step: Any) -> nodes.section | None:
    from ASOkai._pipeline.contracts.file_types import CsvFile

    analysis_type = getattr(step, "analysis_cls", None)
    if analysis_type is None:
        return None
    analysis = documented_section("Analysis", analysis_type)
    if analysis is None:
        analysis = section("Analysis", [])

    csv_outputs = [
        (index, output)
        for index, output in enumerate(step.spec.outputs)
        if isinstance(output.file_type, CsvFile)
    ]
    descriptions = documented_items(analysis_type)
    for output_index, output in csv_outputs:
        analysis += _analysis_output_section(
            output,
            descriptions,
            is_primary=output_index == 0,
            include_output_name=len(csv_outputs) > 1,
        )
    return analysis


def build_step_reference(
    step: Any,
    schema: Mapping[str, Any],
    *,
    refdoc: str = "",
) -> list[nodes.Node]:
    """Build the documentation nodes for one declared step."""
    example_config = _load_example_config()
    identity = nodes.field_list()
    field = nodes.field()
    field += nodes.field_name(text="Step type")
    body = nodes.field_body()
    body += nodes.paragraph(text=_step_kind(step))
    field += body
    identity += field

    result: list[nodes.Node] = [
        nodes.paragraph(text=step.description),
        identity,
    ]
    applicability = _applicability_section(step)
    if applicability is not None:
        result.append(applicability)
    result.extend(
        (
            _invocation_section(step, example_config),
            _dependency_section(step, refdoc=refdoc),
        )
    )

    step_config_fields = collect_step_config_fields(step, schema)
    ordinary_config_fields = [
        field for field in step_config_fields if not field.path.startswith("resources.")
    ]
    resource_config_fields = [
        field for field in step_config_fields if field.path.startswith("resources.")
    ]
    configuration_children: list[nodes.Node] = [config_table(ordinary_config_fields)]
    if resource_config_fields:
        configuration_children.append(
            section(
                "Resources",
                [
                    nodes.paragraph(
                        text=(
                            "Configurable resources use the first value in the "
                            "resolution order shown below."
                        )
                    ),
                    _resources_table(step, resource_config_fields),
                ],
            )
        )
    result.append(section("Configuration", configuration_children))
    rules = rules_section(collect_step_schema_rules(step, schema))
    if rules is not None:
        result.append(rules)

    analysis = _analysis_section(step)
    if analysis is not None:
        result.append(analysis)

    input_children: list[nodes.Node]
    if step.spec.inputs:
        input_children = [_inputs_table(step.spec.inputs, refdoc=refdoc)]
        input_children.append(
            nodes.paragraph(
                text=(
                    "Input override paths are checked for existence. JSON and "
                    "CSV contents are parsed and validated by their contracts; "
                    "opaque formats are passed to the step as filesystem paths."
                )
            )
        )
    else:
        input_children = [nodes.paragraph(text="This step has no file inputs.")]
    result.append(section("Inputs", input_children))

    output_children: list[nodes.Node]
    if step.spec.outputs:
        output_children = [
            nodes.paragraph(
                text=(
                    "File output paths are relative to datadir. Braced names "
                    "are replaced with the corresponding configuration values."
                )
            ),
            section("Scalar outputs", [_scalar_outputs_table()]),
            section(
                "File outputs",
                [
                    _file_outputs_table(
                        step,
                        example_config,
                        refdoc=refdoc,
                    )
                ],
            ),
        ]
    else:
        output_children = [nodes.paragraph(text="This step has no declared outputs.")]
    result.append(section("Outputs", output_children))

    return result


class ASOkaiStepReference(SphinxDirective):
    """Render one built-in step from its runtime contracts."""

    required_arguments = 1

    def run(self) -> list[nodes.Node]:
        try:
            step = get_built_in_step(self.arguments[0])
            schema_path, schema = load_packaged_config_schema()
        except (OSError, ValueError, yaml.YAMLError) as error:
            raise self.error(str(error)) from error
        self.env.note_dependency(str(schema_path))
        self.env.note_dependency(str(EXAMPLE_CONFIG_PATH))
        return build_step_reference(
            step,
            schema,
            refdoc=self.env.docname,
        )


class ASOkaiStepList(SphinxDirective):
    """Render links to built-in steps directly from the runtime registry."""

    required_arguments = 1
    option_spec = {"descriptions": directives.flag}

    def run(self) -> list[nodes.Node]:
        try:
            step_list = build_step_list(
                self.arguments[0],
                include_descriptions="descriptions" in self.options,
                refdoc=self.env.docname,
            )
        except ValueError as error:
            raise self.error(str(error)) from error
        return [step_list]
