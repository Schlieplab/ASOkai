#!/usr/bin/env python
"""
Filename: docs/source/_extensions/contract_docs/file_contracts.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Generated JSON contracts owned by serializable API classes.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

import importlib
import inspect
import json
from abc import ABC
from typing import Any, Mapping

from docutils import nodes
from sphinx import addnodes

from .rendering import (
    code_block,
    note_reference_dependencies,
    section,
    table,
)


def _object_class_name(schema: Mapping[str, Any]) -> str | None:
    properties = schema.get("properties")
    if not isinstance(properties, Mapping):
        return None
    class_schema = properties.get("__class__")
    if not isinstance(class_schema, Mapping):
        return None
    class_name = class_schema.get("const")
    return class_name if isinstance(class_name, str) else None


def _object_module_name(schema: Mapping[str, Any]) -> str | None:
    properties = schema.get("properties")
    if not isinstance(properties, Mapping):
        return None
    module_schema = properties.get("__module__")
    if not isinstance(module_schema, Mapping):
        return None
    module_name = module_schema.get("const")
    return module_name if isinstance(module_name, str) else None


def _serializable_type(schema: Mapping[str, Any]) -> type | None:
    """Return the concrete class identified by an object schema."""
    class_name = _object_class_name(schema)
    module_name = _object_module_name(schema)
    if class_name is None or module_name is None:
        return None
    try:
        serializable_type = getattr(importlib.import_module(module_name), class_name)
    except (AttributeError, ImportError):
        return None
    return serializable_type if isinstance(serializable_type, type) else None


def _object_field_descriptions(schema: Mapping[str, Any]) -> dict[str, str]:
    """Read field descriptions from the serialized class constructor docs."""
    serializable_type = _serializable_type(schema)
    if serializable_type is None:
        return {}

    descriptions: dict[str, str] = {}
    for declaring_type in reversed(serializable_type.__mro__):
        constructor = declaring_type.__dict__.get("__init__")
        if constructor is not None:
            descriptions.update(
                _google_argument_descriptions(inspect.getdoc(constructor))
            )
    return descriptions


def _google_argument_descriptions(docstring: str | None) -> dict[str, str]:
    """Extract simple ``Args:`` entries from an existing docstring."""
    if not docstring:
        return {}
    descriptions: dict[str, str] = {}
    in_arguments = False
    current_name: str | None = None
    for line in docstring.splitlines():
        stripped = line.strip()
        if stripped == "Args:":
            in_arguments = True
            continue
        if not in_arguments:
            continue
        if stripped and not line.startswith((" ", "\t")):
            break
        if not stripped:
            continue
        if ":" in stripped:
            name, description = stripped.split(":", 1)
            if name.replace("_", "").isalnum():
                current_name = name
                descriptions[name] = description.strip()
                continue
        if current_name is not None:
            descriptions[current_name] += f" {stripped}"
    return descriptions


def _format_example(schema: Mapping[str, Any]) -> str:
    if "default" in schema:
        return _format_json_value(schema["default"])
    examples = schema.get("examples")
    if isinstance(examples, list) and examples:
        return _format_json_value(examples[0])
    return "—"


def _format_json_value(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _public_class_path(serializable_type: type) -> str:
    """Return the shortest public module path exporting a class."""
    module_parts = serializable_type.__module__.split(".")
    for length in range(len(module_parts) - 1, 0, -1):
        module_name = ".".join(module_parts[:length])
        try:
            exported_type = getattr(
                importlib.import_module(module_name),
                serializable_type.__name__,
            )
        except (AttributeError, ImportError):
            continue
        if exported_type is serializable_type:
            return f"{module_name}.{serializable_type.__name__}"
    return f"{serializable_type.__module__}.{serializable_type.__name__}"


def class_contract_link(
    serializable_type: type,
    *,
    refdoc: str,
) -> addnodes.pending_xref:
    """Link to the API class that owns a JSON contract."""
    target = _public_class_path(serializable_type)
    link = addnodes.pending_xref(
        "",
        refdoc=refdoc,
        refdomain="py",
        reftype="class",
        reftarget=target,
        refexplicit=True,
        refwarn=True,
    )
    link += nodes.literal(text=serializable_type.__name__)
    return link


def _join_node_groups(
    groups: list[list[nodes.Node]],
    separator: str,
) -> list[nodes.Node]:
    result: list[nodes.Node] = []
    for index, group in enumerate(groups):
        if index:
            result.append(nodes.Text(separator))
        result.extend(group)
    return result


def _schema_value_nodes(
    schema: Mapping[str, Any],
    *,
    refdoc: str,
    multiple: bool = False,
) -> list[nodes.Node]:
    """Describe one schema value and link any ASOkai class it contains."""
    serializable_type = _serializable_type(schema)
    if serializable_type is not None:
        return [
            *([] if multiple else [nodes.Text("a ")]),
            class_contract_link(serializable_type, refdoc=refdoc),
            nodes.Text(" objects" if multiple else " object"),
        ]

    alternatives = schema.get("oneOf", schema.get("anyOf"))
    if isinstance(alternatives, list):
        return _join_node_groups(
            [
                _schema_value_nodes(
                    alternative,
                    refdoc=refdoc,
                    multiple=multiple,
                )
                for alternative in alternatives
                if isinstance(alternative, Mapping)
            ],
            " or ",
        )

    if "const" in schema:
        value = _format_json_value(schema["const"])
        return [nodes.literal(value, value)]
    values = schema.get("enum")
    if isinstance(values, list):
        return _join_node_groups(
            [
                [
                    nodes.literal(
                        _format_json_value(value),
                        _format_json_value(value),
                    )
                ]
                for value in values
            ],
            ", ",
        )

    declared_type = schema.get("type")
    if declared_type == "array":
        item_schema = schema.get("items")
        if isinstance(item_schema, Mapping):
            return [
                nodes.Text("arrays of " if multiple else "an array of "),
                *_schema_value_nodes(
                    item_schema,
                    refdoc=refdoc,
                    multiple=True,
                ),
            ]
    if declared_type == "object":
        value_schema = schema.get("additionalProperties")
        if isinstance(value_schema, Mapping):
            return [
                nodes.Text(
                    "objects mapping string keys to "
                    if multiple
                    else "an object mapping string keys to "
                ),
                *_schema_value_nodes(
                    value_schema,
                    refdoc=refdoc,
                    multiple=True,
                ),
            ]
        return [nodes.Text("objects" if multiple else "an object")]
    if isinstance(declared_type, str):
        plurals = {
            "string": "strings",
            "integer": "integers",
            "number": "numbers",
            "boolean": "booleans",
            "null": "null",
        }
        return [
            nodes.Text(
                plurals.get(declared_type, declared_type) if multiple else declared_type
            )
        ]
    if isinstance(declared_type, list):
        return [nodes.Text(" or ".join(str(value) for value in declared_type))]
    return [nodes.Text("value")]


def _json_details(
    items: list[tuple[str, list[nodes.Node]]],
) -> nodes.container:
    result = nodes.container(classes=["asokai-reference-details"])
    for label, value_nodes in items:
        paragraph = nodes.paragraph()
        paragraph += nodes.strong(text=f"{label}: ")
        paragraph.extend(value_nodes)
        result += paragraph
    return result


def _json_property_table(
    schema: Mapping[str, Any],
    *,
    refdoc: str,
) -> nodes.table:
    """Render only the fields owned directly by one serializable class."""
    properties = schema.get("properties")
    if not isinstance(properties, Mapping):
        raise ValueError("Serializable class schema has no properties.")

    class_name = _object_class_name(schema) or "this class"
    required = set(schema.get("required", ()))
    descriptions = _object_field_descriptions(schema)
    system_descriptions = {
        "__class__": (
            f"Identifies this JSON object as {class_name}. ASOkai writes it "
            "automatically."
        ),
        "__module__": (
            f"Tells ASOkai where {class_name} is defined. ASOkai writes it "
            "automatically."
        ),
    }
    rows = []
    for name, property_schema in properties.items():
        if not isinstance(property_schema, Mapping):
            continue
        requirement = "Required"
        if name in system_descriptions:
            requirement += "; keep unchanged in input files"
        elif name not in required:
            requirement = "Optional"
        item_details = [
            (
                "Accepted value",
                _schema_value_nodes(property_schema, refdoc=refdoc),
            ),
            ("Requirement", [nodes.Text(requirement)]),
        ]
        example = _format_example(property_schema)
        if example != "—":
            item_details.append(("Example", [nodes.literal(example, example)]))
        item_details.append(
            (
                "Meaning",
                [
                    nodes.Text(
                        system_descriptions.get(
                            name,
                            descriptions.get(name, "—"),
                        )
                    )
                ],
            )
        )
        rows.append(((name, True), _json_details(item_details)))

    additional_schema = schema.get("additionalProperties")
    if isinstance(additional_schema, Mapping):
        rows.append(
            (
                ("<extra>", True),
                _json_details(
                    [
                        (
                            "Accepted value",
                            _schema_value_nodes(additional_schema, refdoc=refdoc),
                        ),
                        ("Requirement", [nodes.Text("Optional")]),
                        (
                            "Meaning",
                            [nodes.Text("An additional user-defined scalar field.")],
                        ),
                    ]
                ),
            )
        )

    return table(
        ("JSON field", "Details"),
        rows,
        (25, 75),
        css_class="asokai-json-class-contract",
    )


def _example_from_schema(schema: Mapping[str, Any]) -> Any:
    if "default" in schema:
        return schema["default"]
    if "const" in schema:
        return schema["const"]
    examples = schema.get("examples")
    if isinstance(examples, list) and examples:
        return examples[0]
    values = schema.get("enum")
    if isinstance(values, list) and values:
        return values[0]

    alternatives = schema.get("oneOf", schema.get("anyOf"))
    if isinstance(alternatives, list):
        concrete = [
            alternative
            for alternative in alternatives
            if isinstance(alternative, Mapping)
        ]
        preferred = [
            alternative for alternative in concrete if alternative.get("type") != "null"
        ]
        if preferred or concrete:
            return _example_from_schema((preferred or concrete)[0])

    declared_type = schema.get("type")
    if isinstance(declared_type, list):
        declared_type = next(
            (value for value in declared_type if value != "null"),
            declared_type[0],
        )
    if declared_type == "array":
        item_schema = schema.get("items")
        return (
            [_example_from_schema(item_schema)]
            if isinstance(item_schema, Mapping)
            else []
        )
    if declared_type == "object":
        properties = schema.get("properties")
        required_names = set(schema.get("required", ()))
        if isinstance(properties, Mapping) and properties:
            return {
                name: _example_from_schema(property_schema)
                for name, property_schema in properties.items()
                if name in required_names and isinstance(property_schema, Mapping)
            }
        additional_schema = schema.get("additionalProperties")
        if isinstance(additional_schema, Mapping):
            return {"example": _example_from_schema(additional_schema)}
        return {}
    if declared_type == "string":
        return "example"
    if declared_type == "integer":
        return 1
    if declared_type == "number":
        return 0.5
    if declared_type == "boolean":
        return True
    if declared_type == "null":
        return None
    raise ValueError(f"Cannot generate an example for schema {schema!r}.")


def json_example(file_type: Any) -> str:
    """Return a schema-derived JSON example accepted by a JsonFile contract."""
    from ASOkai._pipeline.contracts.json_schema import build_json_schema

    schema = build_json_schema(file_type.value_type)
    example_data = _example_from_schema(schema)
    inline_content = json.dumps(example_data, indent=4, ensure_ascii=False) + "\n"
    value = file_type.loads(
        inline_content,
        source="generated documentation example",
    )
    return file_type.dumps(value)


def _try_json_example(file_type: Any) -> str | None:
    """Return a valid generated example when structure alone is sufficient."""
    try:
        return json_example(file_type)
    except (TypeError, ValueError):
        return None


def json_contract_types(file_type: Any) -> tuple[type, ...]:
    """Return the classes that own a JsonFile's root value contracts."""
    from ASOkai._pipeline.contracts.json_schema import build_json_schema

    if file_type.value_type is None:
        return ()
    schema = build_json_schema(file_type.value_type)

    def collect(current: Mapping[str, Any]) -> list[type]:
        serializable_type = _serializable_type(current)
        if serializable_type is not None:
            return [serializable_type]

        item_schema = current.get("items")
        if isinstance(item_schema, Mapping):
            return collect(item_schema)

        alternatives = current.get("oneOf", current.get("anyOf"))
        if isinstance(alternatives, list):
            result: list[type] = []
            for alternative in alternatives:
                if isinstance(alternative, Mapping):
                    result.extend(collect(alternative))
            return result
        return []

    return tuple(dict.fromkeys(collect(schema)))


def _serializable_types_in_contract(
    serializable_type: type,
) -> tuple[type, ...]:
    """Return serializable classes used anywhere in one class contract."""
    from ASOkai._pipeline.contracts.json_schema import build_json_schema

    def collect(schema: Mapping[str, Any]) -> list[type]:
        result: list[type] = []
        nested_type = _serializable_type(schema)
        if nested_type is not None:
            result.append(nested_type)

        properties = schema.get("properties")
        if isinstance(properties, Mapping):
            for property_schema in properties.values():
                if isinstance(property_schema, Mapping):
                    result.extend(collect(property_schema))

        for keyword in ("items", "additionalProperties"):
            nested_schema = schema.get(keyword)
            if isinstance(nested_schema, Mapping):
                result.extend(collect(nested_schema))

        for keyword in ("oneOf", "anyOf"):
            alternatives = schema.get(keyword)
            if isinstance(alternatives, list):
                for alternative in alternatives:
                    if isinstance(alternative, Mapping):
                        result.extend(collect(alternative))
        return result

    return tuple(dict.fromkeys(collect(build_json_schema(serializable_type))))


def serializable_contract_nodes(
    serializable_type: type,
    *,
    refdoc: str,
) -> list[nodes.Node]:
    """Build the JSON contract owned by one concrete serializable class."""
    from ASOkai.Utils._serializer import Serializable
    from ASOkai._pipeline.contracts.file_types import JsonFile
    from ASOkai._pipeline.contracts.json_schema import build_json_schema

    if (
        serializable_type is Serializable
        or inspect.isabstract(serializable_type)
        or ABC in serializable_type.__bases__
    ):
        return []
    schema = build_json_schema(serializable_type)
    if _serializable_type(schema) is not serializable_type:
        return []

    class_name = serializable_type.__name__
    contract_id = nodes.make_id(
        f"{_public_class_path(serializable_type)}-json-contract"
    )
    example = _try_json_example(JsonFile(serializable_type))
    fields_section = section(
        "Fields",
        [_json_property_table(schema, refdoc=refdoc)],
    )
    fields_section["ids"] = [f"{contract_id}-fields"]
    contract = nodes.section(ids=[contract_id])
    contract += nodes.title(text="File contract")
    contract += nodes.paragraph(
        text=(
            f"This is the JSON record ASOkai stores for {class_name}. "
            "A JSON file has a root value and an objects table. Objects used "
            "once are inline; repeatedly used objects move to the table and "
            "are linked by references. Nested records follow their own class "
            "contracts."
        )
    )
    contract += nodes.paragraph(
        text=(
            "The __class__ and __module__ fields identify the object "
            "type. ASOkai adds them when writing JSON; keep the fixed "
            "values shown below when supplying an input file yourself."
        )
    )
    if example is not None:
        example_section = section(
            "Example file",
            [code_block(example, "json")],
        )
        example_section["ids"] = [f"{contract_id}-example"]
        contract += example_section
    contract += fields_section
    return [contract]


def append_serializable_contracts(app: Any, doctree: nodes.document) -> None:
    """Append each contract as the final section of its API class entry."""
    from ASOkai.Utils._serializer import Serializable

    contract_source_types: list[type] = []
    for description in doctree.findall(addnodes.desc):
        if description.get("objtype") != "class":
            continue
        signature = next(
            (
                child
                for child in description.children
                if isinstance(child, addnodes.desc_signature)
            ),
            None,
        )
        content = next(
            (
                child
                for child in description.children
                if isinstance(child, addnodes.desc_content)
            ),
            None,
        )
        if signature is None or content is None:
            continue

        module_name = signature.get("module")
        class_name = signature.get("fullname")
        if not isinstance(module_name, str) or not isinstance(class_name, str):
            continue
        try:
            documented_type = getattr(importlib.import_module(module_name), class_name)
        except (AttributeError, ImportError):
            continue
        if not isinstance(documented_type, type) or not issubclass(
            documented_type, Serializable
        ):
            continue
        generated = serializable_contract_nodes(
            documented_type,
            refdoc=app.env.docname,
        )
        if not generated or not isinstance(generated[0], nodes.section):
            continue
        content += generated[0]
        contract_source_types.extend(
            _serializable_types_in_contract(documented_type)
        )

    if contract_source_types:
        note_reference_dependencies(
            app.env,
            tuple(dict.fromkeys(contract_source_types)),
        )
