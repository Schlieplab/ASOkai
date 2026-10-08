#!/usr/bin/env python
"""
Filename: docs/source/_extensions/contract_docs/steps.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Generated references for built-in pipeline steps.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, cast, get_origin

import yaml
from docutils import nodes
from docutils.parsers.rst import directives
from sphinx import addnodes
from sphinx.util.docutils import SphinxDirective

from .configuration import (
    ConditionalParameterGroup,
    collect_conditional_parameter_groups,
    collect_step_config_fields,
    collect_step_schema_rules,
    config_table,
    get_built_in_step,
    get_built_in_steps,
    load_packaged_config_schema,
    rules_section,
)
from .rendering import (
    code_block,
    details,
    document_link,
    documented_items,
    note_reference_dependencies,
    section,
    table,
)

PROJECT_ROOT = Path(__file__).parents[4]
EXAMPLE_CONFIG_PATH = PROJECT_ROOT / "examples/config.example.yaml"


def _path_example(step: Any) -> nodes.literal_block:
    """Build a complete YAML path-override example for one step."""
    suffixes = {
        "application/json": ".json",
        "text/csv": ".csv",
        "application/x-fasta": ".fa",
    }
    inputs = {
        file_input.name: {
            "path": (
                f"/path/to/{file_input.name}"
                f"{suffixes.get(file_input.file_type.media_type, '')}"
            )
        }
        for file_input in step.spec.inputs
    }
    example = yaml.safe_dump(
        {"steps": {step.name: {"inputs": inputs}}},
        sort_keys=False,
    ).rstrip()
    block = nodes.literal_block(example, example)
    block["language"] = "yaml"
    return block


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
    step: Any,
    file_inputs: list[Any] | tuple[Any, ...],
    *,
    refdoc: str,
) -> nodes.table:
    rows = []
    for file_input in file_inputs:
        input_details: list[tuple[str, str | nodes.Node, bool]] = []
        if file_input.source is not None:
            producer_output = nodes.inline()
            producer_output += document_link(
                f"steps/{file_input.source.producer}",
                file_input.source.producer,
                refdoc=refdoc,
            )
            producer_output += nodes.Text(".")
            producer_output += nodes.literal(
                file_input.source.name,
                file_input.source.name,
            )
            input_details.append(("Producer output", producer_output, False))
        configuration_path = file_input.configuration_path(step.name)
        config_source = nodes.inline()
        config_source += nodes.literal(text=f"{configuration_path}.path")
        config_source += nodes.Text(" or ")
        config_source += nodes.literal(text=f"{configuration_path}.from")
        input_details.append(
            (
                "Shared config source",
                config_source,
                False,
            )
        )
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


def _file_outputs_table(
    step: Any,
    example_config: Mapping[str, Any],
    *,
    refdoc: str,
) -> nodes.table:
    rows = []
    parameters = step.resolved_parameter_values(example_config)
    output_config = step._configuration_for_parameters(example_config, parameters)
    example_input_configurations = {
        file_input.name: output_config
        for file_input in step.spec.inputs
    }
    for output in step.spec.outputs:
        example_path = str(
            output.destination.render(
                output_config,
                example_input_configurations,
            )
        )
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
        step_resource_names,
    )

    fields_by_path = {field.path: field for field in config_fields}
    configurable_resources = set(step_resource_names(step))
    rows = []
    for resource_name, fallback in DEFAULT_STEP_RESOURCES.items():
        if resource_name not in configurable_resources:
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
    from ASOkai._pipeline.steps.core.base import CoreStep
    from ASOkai._pipeline.steps.utils.base import UtilityStep

    if not step.listed:
        return "Internal step"
    if isinstance(step, AnalysisStep):
        return "Analysis step"
    if isinstance(step, CoreStep):
        return "Core step"
    if isinstance(step, UtilityStep):
        return "Utility step"
    return "Internal step"


def _built_in_steps_of_kind(step_kind: str) -> tuple[Any, ...]:
    """Return registered built-in steps of one kind."""
    from ASOkai._pipeline.steps.analysis.base import AnalysisStep
    from ASOkai._pipeline.steps.core.base import CoreStep
    from ASOkai._pipeline.steps.utils.base import UtilityStep

    if step_kind == "internal":
        return tuple(step for step in get_built_in_steps() if not step.listed)

    step_types = {
        "analysis": AnalysisStep,
        "core": CoreStep,
        "utils": UtilityStep,
    }
    try:
        step_type = step_types[step_kind]
    except KeyError as error:
        expected = ", ".join((*step_types, "internal"))
        raise ValueError(
            f"Unknown step kind {step_kind!r}; expected one of: {expected}."
        ) from error
    return tuple(
        step
        for step in get_built_in_steps()
        if isinstance(step, step_type) and step.listed
    )


def _step_documentation_sources(steps: tuple[Any, ...]) -> list[object]:
    """Return declarations whose values feed generated step references."""
    from ASOkai._pipeline import catalog

    sources: list[object] = [catalog]
    for step in steps:
        sources.append(step)
        analysis_type = getattr(step, "analysis_cls", None)
        if analysis_type is not None:
            sources.append(analysis_type)
    return sources


def build_step_list(
    step_kind: str,
    *,
    include_descriptions: bool = False,
    refdoc: str = "",
) -> nodes.bullet_list:
    """Build a linked list of registered built-in steps of one kind."""

    step_list = nodes.bullet_list()
    for step in _built_in_steps_of_kind(step_kind):
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


def _step_toctree(step_kind: str, *, parent: str) -> nodes.compound:
    """Build hidden sidebar navigation for one category of steps."""
    docnames = [
        f"steps/{step.name}"
        for step in _built_in_steps_of_kind(step_kind)
    ]
    toctree = addnodes.toctree()
    toctree["parent"] = parent
    toctree["entries"] = [(None, docname) for docname in docnames]
    toctree["includefiles"] = docnames
    toctree["maxdepth"] = 1
    toctree["caption"] = None
    toctree["glob"] = False
    toctree["hidden"] = True
    toctree["includehidden"] = False
    toctree["numbered"] = 0
    toctree["titlesonly"] = False
    wrapper = nodes.compound(classes=["toctree-wrapper"])
    wrapper += toctree
    return wrapper


def _transitive_steps(step: Any) -> list[Any]:
    """Return dependencies followed by the selected step."""
    from ASOkai._pipeline.catalog import _BUILTIN_STEPS

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
    command = f"ASOkai run --step {step.name} --config-file ./config.yaml"
    command_block = nodes.literal_block(command, command)

    example_config = cast(
        str,
        yaml.safe_dump(
            _example_step_config(step, complete_config),
            sort_keys=False,
        ),
    )
    example_description = (
        "Example configuration for this step and its dependencies:"
        if has_dependencies
        else "Example configuration for this step:"
    )
    return section(
        "Run this step",
        [
            command_block,
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
                (35, 65),
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
        (25, 75),
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


def _analysis_output_sections(step: Any) -> list[nodes.section]:
    """Return column documentation nested beneath analysis file outputs."""
    from ASOkai._pipeline.contracts.file_types import CsvFile

    analysis_type = getattr(step, "analysis_cls", None)
    if analysis_type is None:
        return []

    csv_outputs = [
        (index, output)
        for index, output in enumerate(step.spec.outputs)
        if isinstance(output.file_type, CsvFile)
    ]
    descriptions = documented_items(analysis_type)
    output_sections = []
    for output_index, output in csv_outputs:
        output_sections.append(
            _analysis_output_section(
                output,
                descriptions,
                is_primary=output_index == 0,
                include_output_name=len(csv_outputs) > 1,
            )
        )
    return output_sections


def _parameters_section(
    step: Any,
    config_fields: list[Any],
    schema: Mapping[str, Any],
    example_config: Mapping[str, Any],
) -> nodes.section:
    """Document scalar values passed directly to one step."""
    parameter_paths = {
        parameter.config
        for parameter in step.spec.params
        if parameter.config is not None
    }
    parameter_paths.update(step.spec.compatible_with)
    parameter_fields = [
        field for field in config_fields if field.path in parameter_paths
    ]
    conditional_groups = collect_conditional_parameter_groups(
        parameter_fields,
        schema,
    )
    conditional_paths = {
        group.discriminator.path
        for group in conditional_groups
    }
    conditional_paths.update(
        field.path
        for group in conditional_groups
        for fields in group.alternatives.values()
        for field in fields
    )
    common_fields = [
        field for field in parameter_fields if field.path not in conditional_paths
    ]
    children: list[nodes.Node] = []
    if common_fields:
        parameter_table = config_table(common_fields)
        if conditional_groups:
            parameter_table = section(
                "Common parameters",
                [parameter_table],
            )
        children.extend(
            (
                nodes.paragraph(
                    text="These scalar configuration values are passed to this step."
                ),
                parameter_table,
            )
        )
    elif not conditional_groups:
        children.append(
            nodes.paragraph(text="This step has no scalar parameters.")
        )

    children.extend(
        _conditional_parameter_section(group, example_config)
        for group in conditional_groups
    )
    explained_rules = {
        rule
        for group in conditional_groups
        for rule in group.explained_rules
    }
    remaining_rules = [
        rule
        for rule in collect_step_schema_rules(step, schema)
        if rule not in explained_rules
    ]
    rules = rules_section(remaining_rules)
    if rules is not None:
        children.append(rules)
    return section("Parameters", children)


def _conditional_parameter_section(
    group: ConditionalParameterGroup,
    example_config: Mapping[str, Any],
) -> nodes.section:
    """Render one schema-defined set of parameter alternatives."""
    parent_name = group.discriminator.path.split(".")[-2]
    alternatives: list[nodes.Node] = []
    for value, fields in group.alternatives.items():
        description = nodes.paragraph()
        description += nodes.Text("Set ")
        description += nodes.literal(
            group.discriminator.path,
            group.discriminator.path,
        )
        description += nodes.Text(" to ")
        description += nodes.literal(value, value)
        description += nodes.Text(".")

        variant_config: dict[str, Any] = {}
        _assign_path(variant_config, group.discriminator.path, value)
        for field in fields:
            example_value = _resolve_optional(example_config, field.path)
            if example_value is not None:
                _assign_path(variant_config, field.path, example_value)
        example = yaml.safe_dump(variant_config, sort_keys=False).rstrip()

        variant_children: list[nodes.Node] = [
            description,
            nodes.paragraph(text="Example configuration:"),
            code_block(example, "yaml"),
        ]
        if fields:
            variant_children.append(config_table(list(fields)))
        else:
            variant_children.append(
                nodes.paragraph(
                    text="This option has no additional parameters."
                )
            )
        value_label = str(value).replace("-", " ").capitalize()
        alternatives.append(
            section(f"{value_label} {parent_name}", variant_children)
        )
    group_title = f"{parent_name.capitalize()}s"
    return section(group_title, alternatives)


def _inputs_section(step: Any, *, refdoc: str) -> nodes.section:
    """Document file inputs together with their producer dependencies."""
    if not step.spec.inputs:
        return section(
            "Inputs",
            [
                nodes.paragraph(
                    text="This step has no file inputs or producer dependencies."
                )
            ],
        )

    return section(
        "Inputs",
        [
            nodes.paragraph(
                text=(
                    "An input with a fixed producer uses that output by "
                    "default. A selected run can instead link a named output "
                    "or supply an existing path. The input's path override "
                    "in config.yaml also selects an existing file. External "
                    "paths are validated against the input's file contract."
                )
            ),
            _inputs_table(step, step.spec.inputs, refdoc=refdoc),
            nodes.paragraph(text="Example path-override configuration:"),
            _path_example(step),
        ],
    )


def _resources_section(step: Any, config_fields: list[Any]) -> nodes.section | None:
    """Document configurable compute resources, when the step has any."""
    resource_fields = [
        field for field in config_fields if field.path.startswith("resources.")
    ]
    if not resource_fields:
        return None
    return section(
        "Resources",
        [
            nodes.paragraph(
                text=(
                    "Configurable resources use the first value in the "
                    "resolution order shown below."
                )
            ),
            _resources_table(step, resource_fields),
        ],
    )


def _outputs_section(
    step: Any,
    example_config: Mapping[str, Any],
    *,
    refdoc: str,
) -> nodes.section:
    """Document scalar and file outputs, including analysis table columns."""
    if not step.spec.outputs:
        return section(
            "Outputs",
            [nodes.paragraph(text="This step has no declared outputs.")],
        )

    children: list[nodes.Node] = [
        nodes.paragraph(
            text=(
                "File output paths are relative to datadir. Braced names "
                "are replaced with the corresponding parameter values."
            )
        ),
        section(
            "File outputs",
            [_file_outputs_table(step, example_config, refdoc=refdoc)],
        ),
    ]
    children.extend(_analysis_output_sections(step))
    return section("Outputs", children)


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
    result.append(_invocation_section(step, example_config))
    step_config_fields = collect_step_config_fields(step, schema)
    result.append(
        _parameters_section(
            step,
            step_config_fields,
            schema,
            example_config,
        )
    )
    result.append(_inputs_section(step, refdoc=refdoc))
    resources = _resources_section(step, step_config_fields)
    if resources is not None:
        result.append(resources)
    result.append(_outputs_section(step, example_config, refdoc=refdoc))

    return result


class ASOkaiStepReference(SphinxDirective):
    """Render one built-in step from its runtime contracts."""

    required_arguments = 1

    def run(self) -> list[nodes.Node]:
        try:
            step = get_built_in_step(self.arguments[0])
            schema_path, schema = load_packaged_config_schema()
            included_steps = tuple(_transitive_steps(step))
            result = build_step_reference(
                step,
                schema,
                refdoc=self.env.docname,
            )
        except (
            KeyError,
            OSError,
            TypeError,
            ValueError,
            yaml.YAMLError,
        ) as error:
            raise self.error(str(error)) from error
        note_reference_dependencies(
            self.env,
            _step_documentation_sources(included_steps),
            paths=(schema_path, EXAMPLE_CONFIG_PATH),
        )
        return result


class ASOkaiStepList(SphinxDirective):
    """Render links to built-in steps directly from the runtime registry."""

    required_arguments = 1
    option_spec = {"descriptions": directives.flag}

    def run(self) -> list[nodes.Node]:
        try:
            step_kind = self.arguments[0]
            steps = _built_in_steps_of_kind(step_kind)
            step_list = build_step_list(
                step_kind,
                include_descriptions="descriptions" in self.options,
                refdoc=self.env.docname,
            )
            step_toctree = _step_toctree(
                step_kind,
                parent=self.env.docname,
            )
        except ValueError as error:
            raise self.error(str(error)) from error
        note_reference_dependencies(
            self.env,
            _step_documentation_sources(steps),
        )
        if step_kind == "internal" and not steps:
            return [nodes.paragraph(text="There are no built-in internal steps currently.")]
        self.set_source_info(step_toctree)
        return [step_list, step_toctree]
