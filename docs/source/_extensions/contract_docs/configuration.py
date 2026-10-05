#!/usr/bin/env python
"""
Filename: docs/source/_extensions/contract_docs/configuration.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Configuration-schema collection and rendering.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Mapping

from docutils import nodes

from .rendering import details, section, table


@dataclass(frozen=True)
class ConfigField:
    """One documented leaf in a configuration schema."""

    path: str
    value_type: str
    requirement: str
    constraints: str
    description: str


@dataclass(frozen=True)
class ConditionalParameterGroup:
    """Parameters selected by one configuration value."""

    discriminator: ConfigField
    alternatives: Mapping[str, tuple[ConfigField, ...]]
    explained_rules: frozenset[str]


def _collect_config_fields(schema: Mapping[str, Any]) -> list[ConfigField]:
    """Collect documented leaf fields from a nested object schema."""
    fields: list[ConfigField] = []
    _collect_object_fields(
        schema,
        fields,
        prefix="",
        parent_is_required=True,
        named_entry=False,
    )
    choice_requirements = _choice_requirements(schema)
    return [
        replace(
            field,
            requirement=choice_requirements.get(field.path, field.requirement),
        )
        for field in fields
    ]


def _choice_requirements(
    schema: Mapping[str, Any],
    *,
    prefix: str = "",
) -> dict[str, str]:
    """Describe simple one-of required-field choices in an object schema."""
    requirements: dict[str, str] = {}
    for condition in schema.get("allOf", ()):
        if not isinstance(condition, Mapping):
            continue
        choices = condition.get("oneOf")
        if not isinstance(choices, list):
            continue
        required_choices = [
            tuple(choice.get("required", ()))
            for choice in choices
            if isinstance(choice, Mapping)
        ]
        if not required_choices or any(
            len(required_names) != 1 for required_names in required_choices
        ):
            continue
        names = [required_names[0] for required_names in required_choices]
        requirement = (
            f"Exactly one of {', '.join(names)} is required when "
            f"{prefix or 'this section'} is configured"
        )
        for name in names:
            path = f"{prefix}.{name}" if prefix else name
            requirements[path] = requirement

    properties = schema.get("properties")
    if isinstance(properties, Mapping):
        for name, child_schema in properties.items():
            if not isinstance(child_schema, Mapping):
                continue
            path = f"{prefix}.{name}" if prefix else name
            requirements.update(_choice_requirements(child_schema, prefix=path))
    return requirements


def _collect_object_fields(
    schema: Mapping[str, Any],
    fields: list[ConfigField],
    *,
    prefix: str,
    parent_is_required: bool,
    named_entry: bool,
) -> None:
    required_names = set(schema.get("required", ()))
    properties = schema.get("properties", {})
    if isinstance(properties, Mapping):
        for name, field_schema in properties.items():
            if not isinstance(field_schema, Mapping):
                continue
            path = f"{prefix}.{name}" if prefix else name
            field_is_required = name in required_names
            _collect_config_field(
                field_schema,
                fields,
                path=path,
                parent_path=prefix,
                field_is_required=field_is_required,
                always_required=(parent_is_required and field_is_required),
                named_entry=named_entry,
            )

    additional_schema = schema.get("additionalProperties")
    if isinstance(additional_schema, Mapping):
        path = f"{prefix}.<name>" if prefix else "<name>"
        _collect_config_field(
            additional_schema,
            fields,
            path=path,
            parent_path=prefix,
            field_is_required=False,
            always_required=False,
            named_entry=True,
        )


def _collect_config_field(
    schema: Mapping[str, Any],
    fields: list[ConfigField],
    *,
    path: str,
    parent_path: str,
    field_is_required: bool,
    always_required: bool,
    named_entry: bool,
) -> None:
    if _is_object_schema(schema):
        _collect_object_fields(
            schema,
            fields,
            prefix=path,
            parent_is_required=always_required,
            named_entry=named_entry,
        )
        return

    if always_required:
        requirement = "Required"
    elif field_is_required:
        requirement = f"Required when {parent_path} is configured"
    elif "default" in schema and schema.get("const") == schema["default"]:
        requirement = f"Default and only value: {_format_value(schema['default'])}"
    elif "default" in schema:
        requirement = f"Default: {_format_value(schema['default'])}"
    elif named_entry:
        requirement = "Optional for each configured name"
    else:
        requirement = "Optional"

    fields.append(
        ConfigField(
            path=path,
            value_type=_format_schema_type(schema),
            requirement=requirement,
            constraints=_format_constraints(schema),
            description=str(schema.get("description", "—")),
        )
    )


def _is_object_schema(schema: Mapping[str, Any]) -> bool:
    return (
        schema.get("type") == "object"
        or isinstance(schema.get("properties"), Mapping)
        or isinstance(schema.get("additionalProperties"), Mapping)
    )


def _format_schema_type(schema: Mapping[str, Any]) -> str:
    alternatives = schema.get("oneOf", schema.get("anyOf"))
    if isinstance(alternatives, list):
        labels = [
            _schema_label(alternative)
            for alternative in alternatives
            if isinstance(alternative, Mapping)
        ]
        if labels:
            return " or ".join(dict.fromkeys(labels))

    declared_type = schema.get("type")
    if isinstance(declared_type, str):
        return declared_type
    if isinstance(declared_type, list):
        return " or ".join(str(value) for value in declared_type)

    values = schema.get("enum")
    if not isinstance(values, list) and "const" in schema:
        values = [schema["const"]]
    if isinstance(values, list) and values:
        value_types = {_json_type(value) for value in values}
        if len(value_types) == 1:
            return value_types.pop()
    return "value"


def _schema_label(schema: Mapping[str, Any]) -> str:
    properties = schema.get("properties")
    if isinstance(properties, Mapping):
        class_schema = properties.get("__class__")
        if isinstance(class_schema, Mapping):
            class_name = class_schema.get("const")
            if isinstance(class_name, str):
                return class_name
    return _format_schema_type_without_alternatives(schema)


def _format_schema_type_without_alternatives(
    schema: Mapping[str, Any],
) -> str:
    declared_type = schema.get("type")
    if isinstance(declared_type, str):
        return declared_type
    if isinstance(declared_type, list):
        return " or ".join(str(value) for value in declared_type)
    if "const" in schema:
        return _json_type(schema["const"])
    values = schema.get("enum")
    if isinstance(values, list) and values:
        types = {_json_type(value) for value in values}
        if len(types) == 1:
            return types.pop()
    return "value"


def _json_type(value: Any) -> str:
    if value is None:
        return "null"
    if type(value) is bool:
        return "boolean"
    if type(value) is int:
        return "integer"
    if type(value) is float:
        return "number"
    if type(value) is str:
        return "string"
    if type(value) is list:
        return "array"
    if type(value) is dict:
        return "object"
    return "value"


def _format_constraints(schema: Mapping[str, Any]) -> str:
    constraints: list[str] = []
    if "const" in schema and schema.get("default") != schema["const"]:
        constraints.append(f"fixed: {_format_value(schema['const'])}")
    if isinstance(schema.get("enum"), list):
        allowed = ", ".join(_format_value(value) for value in schema["enum"])
        constraints.append(f"one of: {allowed}")

    labels = {
        "minimum": "minimum",
        "maximum": "maximum",
        "exclusiveMinimum": "greater than",
        "exclusiveMaximum": "less than",
        "minLength": "minimum string length",
        "maxLength": "maximum string length",
        "pattern": "pattern",
    }
    for keyword, label in labels.items():
        if keyword in schema:
            constraints.append(f"{label}: {_format_value(schema[keyword])}")
    return "; ".join(constraints) if constraints else "—"


def _format_value(value: Any) -> str:
    if value is None:
        return "null"
    if type(value) is bool:
        return "true" if value else "false"
    return str(value)


def _collect_schema_rules(
    schema: Mapping[str, Any],
    *,
    path: str = "",
) -> list[tuple[str, str]]:
    rules: list[tuple[str, str]] = []
    message = schema.get("x-error-message")
    if isinstance(message, str):
        rules.append((path, message))

    properties = schema.get("properties")
    if isinstance(properties, Mapping):
        for name, field_schema in properties.items():
            if isinstance(field_schema, Mapping):
                field_path = f"{path}.{name}" if path else name
                rules.extend(_collect_schema_rules(field_schema, path=field_path))

    for keyword in ("allOf", "anyOf", "oneOf"):
        alternatives = schema.get(keyword)
        if isinstance(alternatives, list):
            for alternative in alternatives:
                if isinstance(alternative, Mapping):
                    rules.extend(_collect_schema_rules(alternative, path=path))
    return list(dict.fromkeys(rules))


def get_built_in_steps() -> tuple[Any, ...]:
    """Return the built-in steps in their registered pipeline order."""
    from ASOkai._pipeline.catalog import _BUILTIN_STEPS

    return tuple(_BUILTIN_STEPS)


def get_built_in_step(step_name: str) -> Any:
    """Return one built-in step by its public name."""
    built_in_steps = get_built_in_steps()
    for step in built_in_steps:
        if step.name == step_name:
            return step
    available = ", ".join(step.name for step in built_in_steps)
    raise ValueError(
        f"Unknown built-in step {step_name!r}; expected one of: {available}."
    )


def _output_template_fields(step: Any) -> list[Any]:
    """Return main-configuration fields used by declared output paths."""
    from ASOkai._pipeline.contracts.paths import TemplateField

    return [
        template_field
        for output in step.spec.outputs
        for template_field in output.destination.fields.values()
        if isinstance(template_field, TemplateField)
    ]


def collect_step_config_fields(
    step: Any,
    schema: Mapping[str, Any],
) -> list[ConfigField]:
    """Return only the configuration fields used to run one step."""
    all_fields = {field.path: field for field in _collect_config_fields(schema)}
    fields: list[ConfigField] = []
    added_paths: set[str] = set()

    def add(field: ConfigField) -> None:
        if field.path not in added_paths:
            fields.append(field)
            added_paths.add(field.path)

    add(all_fields["datadir"])
    add(all_fields["validation.existing_outputs"])
    for parameter in step.spec.params:
        if parameter.config is None or parameter.config in added_paths:
            continue
        field = all_fields[parameter.config]
        requirement = field.requirement
        if requirement == "Optional" and parameter.parser_required():
            requirement = "Required"
        add(replace(field, requirement=requirement))

    for template_field in _output_template_fields(step):
        config_paths = template_field.config_paths()
        for path in config_paths:
            field = all_fields[path]
            requirement = field.requirement
            if (
                requirement == "Optional"
                and len(config_paths) == 1
                and template_field.default is None
            ):
                requirement = "Required to determine the output path"
            add(replace(field, requirement=requirement))

    for path in step.spec.compatible_with:
        if path in added_paths:
            continue
        add(
            replace(
                all_fields[path],
                requirement="Required to determine step compatibility",
            )
        )

    for file_input in step.spec.inputs:
        configuration_path = file_input.configuration_path(step.name)
        for source_name in ("path", "from"):
            generic_path = f"steps.<name>.inputs.<name>.{source_name}"
            add(
                replace(
                    all_fields[generic_path],
                    path=f"{configuration_path}.{source_name}",
                    requirement="Choose path or from",
                )
            )

    from ASOkai._pipeline.config import (
        DEFAULT_STEP_RESOURCES,
        step_resource_names,
    )

    for resource_name in step_resource_names(step):
        default = DEFAULT_STEP_RESOURCES[resource_name]
        default_path = f"resources.default.{resource_name}"
        add(
            replace(
                all_fields[default_path],
                requirement=f"Built-in fallback: {_format_value(default)}",
            )
        )
        named_field = all_fields[f"resources.<name>.{resource_name}"]
        add(
            replace(
                named_field,
                path=f"resources.{step.name}.{resource_name}",
                requirement="Overrides resources.default",
            )
        )
    return fields


def collect_step_schema_rules(
    step: Any,
    schema: Mapping[str, Any],
) -> list[str]:
    """Return schema rules that mention configuration used by one step."""
    paths = {
        parameter.config
        for parameter in step.spec.params
        if parameter.config is not None
    }
    paths.update(
        path
        for template_field in _output_template_fields(step)
        for path in template_field.config_paths()
    )
    for file_input in step.spec.inputs:
        configuration_path = file_input.configuration_path(step.name)
        paths.add(f"{configuration_path}.path")
        paths.add(f"{configuration_path}.from")
    paths.update(step.spec.compatible_with)
    return [
        message
        for rule_path, message in _collect_schema_rules(schema)
        if not rule_path
        or any(path == rule_path or path.startswith(f"{rule_path}.") for path in paths)
    ]


def collect_conditional_parameter_groups(
    config_fields: list[ConfigField],
    schema: Mapping[str, Any],
) -> list[ConditionalParameterGroup]:
    """Return schema-defined alternatives among documented parameters."""
    fields_by_path = {field.path: field for field in config_fields}
    groups: list[ConditionalParameterGroup] = []

    def visit(current: Mapping[str, Any], path: str) -> None:
        alternatives_by_field: dict[str, dict[str, dict[str, set[str]]]] = {}
        rules_by_field: dict[str, set[str]] = {}
        branches = current.get("allOf")
        if isinstance(branches, list):
            for branch in branches:
                if not isinstance(branch, Mapping):
                    continue
                condition = branch.get("if")
                consequence = branch.get("then")
                if not isinstance(condition, Mapping) or not isinstance(
                    consequence,
                    Mapping,
                ):
                    continue
                condition_properties = condition.get("properties")
                if not isinstance(condition_properties, Mapping):
                    continue
                discriminators = [
                    (name, field_schema["const"])
                    for name, field_schema in condition_properties.items()
                    if isinstance(field_schema, Mapping)
                    and isinstance(field_schema.get("const"), str)
                ]
                if len(discriminators) != 1:
                    continue
                discriminator_name, discriminator_value = discriminators[0]
                discriminator_path = (
                    f"{path}.{discriminator_name}"
                    if path
                    else discriminator_name
                )
                if discriminator_path not in fields_by_path:
                    continue

                required = {
                    name
                    for name in consequence.get("required", ())
                    if isinstance(name, str)
                }
                included = set(required)
                consequence_properties = consequence.get("properties")
                if isinstance(consequence_properties, Mapping):
                    included.update(
                        name
                        for name in consequence_properties
                        if isinstance(name, str)
                    )
                excluded: set[str] = set()
                negated = consequence.get("not")
                if isinstance(negated, Mapping):
                    forbidden_branches = negated.get("anyOf")
                    if isinstance(forbidden_branches, list):
                        for forbidden_branch in forbidden_branches:
                            if not isinstance(forbidden_branch, Mapping):
                                continue
                            excluded.update(
                                name
                                for name in forbidden_branch.get("required", ())
                                if isinstance(name, str)
                            )

                alternatives_by_field.setdefault(
                    discriminator_path,
                    {},
                )[discriminator_value] = {
                    "included": included,
                    "required": required,
                    "excluded": excluded,
                }
                for source in (branch, consequence):
                    message = source.get("x-error-message")
                    if isinstance(message, str):
                        rules_by_field.setdefault(
                            discriminator_path,
                            set(),
                        ).add(message)

        for discriminator_path, alternatives in alternatives_by_field.items():
            if len(alternatives) < 2:
                continue
            documented_alternatives: dict[str, tuple[ConfigField, ...]] = {}
            for value, declarations in alternatives.items():
                fields: list[ConfigField] = []
                included_paths = {
                    f"{path}.{name}" if path else name
                    for name in declarations["included"]
                    - declarations["excluded"]
                }
                for field in config_fields:
                    if field.path not in included_paths:
                        continue
                    name = field.path.rsplit(".", maxsplit=1)[-1]
                    requirement = (
                        f"Required when {discriminator_path} is {value}"
                        if name in declarations["required"]
                        else f"Optional when {discriminator_path} is {value}"
                    )
                    fields.append(replace(field, requirement=requirement))
                documented_alternatives[value] = tuple(fields)
            groups.append(
                ConditionalParameterGroup(
                    discriminator=fields_by_path[discriminator_path],
                    alternatives=documented_alternatives,
                    explained_rules=frozenset(
                        rules_by_field.get(discriminator_path, ())
                    ),
                )
            )

        properties = current.get("properties")
        if isinstance(properties, Mapping):
            for name, child in properties.items():
                if isinstance(child, Mapping):
                    child_path = f"{path}.{name}" if path else name
                    visit(child, child_path)

    visit(schema, "")
    return groups


def config_table(fields: list[ConfigField]) -> nodes.table:
    """Render configuration fields as a compact table."""
    rows = []
    for field in fields:
        accepted_value = field.value_type
        if field.constraints != "—":
            accepted_value += f"; {field.constraints}"
        field_details = [
            ("Accepted value", accepted_value, False),
            ("Requirement", field.requirement, False),
        ]
        field_details.append(("Description", field.description, False))
        rows.append(((field.path, True), details(field_details)))
    return table(
        ("Configuration path", "Details"),
        rows,
        (35, 65),
        css_class="asokai-step-configuration",
    )


def rules_section(rules: list[str]) -> nodes.section | None:
    """Render cross-parameter rules under a real heading."""
    if not rules:
        return None
    rule_list = nodes.bullet_list()
    for rule in rules:
        item = nodes.list_item()
        item += nodes.paragraph(text=rule)
        rule_list += item
    return section("Parameter rules", [rule_list])


def load_packaged_config_schema() -> tuple[Path, Mapping[str, Any]]:
    """Load ASOkai's packaged configuration schema."""
    import ASOkai._pipeline.config as config_module

    schema_path = Path(config_module.__file__).with_name("config.schema.yaml")
    schema = config_module.load_config_schema(schema_path, "ASOkai")
    return schema_path, schema
