#!/usr/bin/env python
"""
Filename: src/ASOkai/_pipeline/contracts/json_schema.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Recursive JSON schemas for Serializable values.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

import inspect
import re
from abc import ABC
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import fields, is_dataclass
from types import NoneType, UnionType
from typing import (
    Any,
    Literal,
    TypeAlias,
    Union,
    get_args,
    get_origin,
    get_type_hints,
)

from Bio.Seq import Seq
from jsonschema.validators import validator_for

from ASOkai.Utils._serializer import Serializable


JsonSchema: TypeAlias = dict[str, Any]
JsonData: TypeAlias = (
    str
    | int
    | float
    | bool
    | None
    | Mapping[str, "JsonData"]
    | Sequence["JsonData"]
)


def build_json_schema(expected_type: Any) -> JsonSchema:
    """Build a JSON schema recursively from Serializable annotations."""
    title = json_file_type_name(expected_type)
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": title,
        **_build_schema(expected_type),
    }


def build_json_graph_schema(expected_type: Any) -> JsonSchema:
    """Build the JSON schema for a typed Serializable graph document."""
    title = json_file_type_name(expected_type)
    record_types = _graph_serializable_types(expected_type)
    definition_names = {
        serializable_type: f"record_{index}"
        for index, serializable_type in enumerate(record_types)
    }
    record_schemas_by_name: dict[str, list[JsonSchema]] = {}
    for serializable_type in record_types:
        record_schemas_by_name.setdefault(serializable_type.__name__, []).append(
            {"$ref": f"#/$defs/{definition_names[serializable_type]}"}
        )
    record_patterns = {
        rf"^{re.escape(class_name)}(?:-[0-9]+)?$": (
            schemas[0] if len(schemas) == 1 else {"oneOf": schemas}
        )
        for class_name, schemas in record_schemas_by_name.items()
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": title,
        "type": "object",
        "additionalProperties": False,
        "required": ["root", "objects"],
        "$defs": {
            definition_names[serializable_type]: _build_graph_record_schema(
                serializable_type,
                definition_names,
            )
            for serializable_type in record_types
        },
        "properties": {
            "root": _build_graph_value_schema(expected_type, definition_names),
            "objects": {
                "type": "object",
                "additionalProperties": False,
                "patternProperties": record_patterns,
            },
        },
    }


def json_schema_errors(
    schema: JsonSchema,
    data: Any,
) -> list[str]:
    """Return every validation issue in data as a readable JSON path."""
    validator_class = validator_for(schema)
    validator_class.check_schema(schema)
    errors = sorted(
        validator_class(schema).iter_errors(data),
        key=lambda error: (
            tuple(str(part) for part in error.absolute_path),
            error.message,
        ),
    )
    return [
        f"{_json_path(error.absolute_path)}: "
        f"{_schema_error_message(error)}"
        for error in errors
    ]


def validate_json_data(
    expected_type: Any,
    json_data: JsonData,
) -> None:
    """Raise one error containing every schema issue in a JSON document."""
    expected_type_name = json_file_type_name(expected_type)
    schema = build_json_schema(expected_type)
    errors = json_schema_errors(schema, json_data)
    if not errors:
        return

    details = "\n".join(
        f"- {error}"
        for error in errors
    )
    raise ValueError(
        f"JSON does not match the {expected_type_name} schema:\n{details}"
    )


def validate_json_graph_data(
    expected_type: Any,
    json_data: JsonData,
) -> None:
    """Raise one error containing every graph-document schema issue."""
    expected_type_name = json_file_type_name(expected_type)
    schema = build_json_graph_schema(expected_type)
    if _graph_schema_matches_fast(expected_type, json_data, schema):
        return
    errors = json_schema_errors(schema, json_data)
    if not errors:
        return

    details = "\n".join(f"- {error}" for error in errors)
    raise ValueError(
        f"JSON does not match the {expected_type_name} graph schema:\n{details}"
    )


def _graph_schema_matches_fast(
    expected_type: Any,
    data: Any,
    schema: JsonSchema,
) -> bool:
    """Validate tagged records directly, avoiding repeated subtype trials."""
    if (
        not isinstance(data, dict)
        or set(data) != {"root", "objects"}
        or not isinstance(data["objects"], dict)
    ):
        return False

    record_types = _graph_serializable_types(expected_type)
    validator_class = validator_for(schema)
    definitions = schema["$defs"]
    record_validators = {
        (record_type.__module__, record_type.__name__): validator_class(
            {
                "$schema": schema["$schema"],
                "$defs": definitions,
                "$ref": f"#/$defs/record_{index}",
            }
        )
        for index, record_type in enumerate(record_types)
    }
    reference_validator = validator_class(_build_graph_reference_schema())

    def record_matches(value: Any, allowed_types: set[type[Serializable]]) -> bool:
        if not isinstance(value, dict):
            return False
        if "$ref" in value:
            return not any(reference_validator.iter_errors(value))
        tag = (value.get("__module__"), value.get("__class__"))
        record_type = next(
            (
                candidate
                for candidate in allowed_types
                if (candidate.__module__, candidate.__name__) == tag
            ),
            None,
        )
        if record_type is None:
            return False
        validator_key = (record_type.__module__, record_type.__name__)
        return not any(record_validators[validator_key].iter_errors(value))

    def root_matches(value: Any, declared_type: Any) -> bool:
        if get_origin(declared_type) is list:
            item_type = get_args(declared_type)[0]
            return isinstance(value, list) and all(
                root_matches(item, item_type) for item in value
            )
        allowed_types = set(
            _concrete_serializable_types(declared_type)
            if _is_abstract_serializable(declared_type)
            else [declared_type]
        )
        return record_matches(value, allowed_types)

    if not root_matches(data["root"], expected_type):
        return False
    all_record_types = set(record_types)
    for key, record in data["objects"].items():
        if not isinstance(record, dict):
            return False
        class_name = record.get("__class__")
        if (
            type(key) is not str
            or type(class_name) is not str
            or re.fullmatch(rf"{re.escape(class_name)}(?:-[0-9]+)?", key) is None
            or not record_matches(record, all_record_types)
        ):
            return False
    return True


def _build_schema(
    expected_type: Any,
) -> JsonSchema:
    """Return the JSON representation of one annotated Python type."""
    origin = get_origin(expected_type)
    arguments = get_args(expected_type)

    if origin is list:
        if len(arguments) != 1:
            raise TypeError("JSON list annotations require one item type.")
        return {
            "type": "array",
            "items": _build_schema(arguments[0]),
        }

    if origin in (dict, Mapping):
        if len(arguments) != 2 or arguments[0] is not str:
            raise TypeError(
                "JSON mapping annotations must have string keys and one "
                "value type."
            )
        return {
            "type": "object",
            "additionalProperties": _build_schema(arguments[1]),
        }

    if origin is Literal:
        return {"enum": list(arguments)}

    if origin in (Union, UnionType):
        return {
            "anyOf": [
                _build_schema(argument)
                for argument in arguments
            ]
        }

    scalar_types = {
        str: "string",
        int: "integer",
        float: "number",
        bool: "boolean",
        NoneType: "null",
    }
    if expected_type in scalar_types:
        return {"type": scalar_types[expected_type]}
    if expected_type is Seq:
        return {
            "type": "string",
            "examples": ["A"],
        }

    if isinstance(expected_type, type) and issubclass(
        expected_type,
        Serializable,
    ):
        allowed_types = (
            _concrete_serializable_types(expected_type)
            if _is_abstract_serializable(expected_type)
            else [expected_type]
        )
        schemas = [
            _build_object_schema(allowed_type)
            for allowed_type in allowed_types
        ]
        return schemas[0] if len(schemas) == 1 else {"oneOf": schemas}

    if isinstance(expected_type, type) and is_dataclass(expected_type):
        return _build_dataclass_schema(expected_type)

    raise TypeError(
        f"{expected_type!r} has no JSON representation."
    )


def _build_dataclass_schema(dataclass_type: type[Any]) -> JsonSchema:
    """Build the object schema for a JSON-compatible dataclass."""
    field_types = get_type_hints(dataclass_type)
    serialized_fields = [
        field
        for field in fields(dataclass_type)
        if field.init
    ]
    properties = {
        field.name: _build_schema(field_types.get(field.name, field.type))
        for field in serialized_fields
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": list(properties),
        "properties": properties,
    }


def _build_object_schema(
    serializable_type: type[Serializable],
) -> JsonSchema:
    """Build the object schema for one concrete Serializable class."""
    serialized_fields = serializable_type._serialized_field_types()
    properties = {
        field_name: _build_schema(
            field_type,
        )
        for field_name, field_type in serialized_fields.items()
    }
    constructor_parameters = serializable_type._constructor_parameters()
    _add_constructor_defaults(constructor_parameters, properties)
    schema: JsonSchema = {
        "type": "object",
        "additionalProperties": (
            True
            if serializable_type._accepts_extra_fields()
            else False
        ),
        "required": [
            "__class__",
            "__module__",
            *properties,
        ],
        "properties": {
            "__class__": {"const": serializable_type.__name__},
            "__module__": {"const": serializable_type.__module__},
            **properties,
        },
    }
    constructor_only_parameters = _constructor_only_parameters(
        constructor_parameters,
        serialized_fields,
    )
    if constructor_only_parameters:
        schema["propertyNames"] = {
            "not": {"enum": constructor_only_parameters},
        }
    return schema


def _build_graph_value_schema(
    expected_type: Any,
    definition_names: Mapping[type[Serializable], str],
) -> JsonSchema:
    """Build a schema for inline records or object-table references."""
    origin = get_origin(expected_type)
    arguments = get_args(expected_type)

    if origin is list:
        return {
            "type": "array",
            "items": _build_graph_value_schema(arguments[0], definition_names),
        }
    if origin in (dict, Mapping):
        return {
            "type": "object",
            "additionalProperties": _build_graph_value_schema(
                arguments[1], definition_names
            ),
        }
    if origin is Literal:
        return {"enum": list(arguments)}
    if origin in (Union, UnionType):
        return {
            "anyOf": [
                _build_graph_value_schema(argument, definition_names)
                for argument in arguments
            ]
        }
    if isinstance(expected_type, type) and issubclass(
        expected_type,
        Serializable,
    ):
        concrete_types = (
            _concrete_serializable_types(expected_type)
            if _is_abstract_serializable(expected_type)
            else [expected_type]
        )
        inline_schemas = [
            {"$ref": f"#/$defs/{definition_names[serializable_type]}"}
            for serializable_type in concrete_types
        ]
        inline_schema = (
            inline_schemas[0]
            if len(inline_schemas) == 1
            else {"oneOf": inline_schemas}
        )
        return {
            "if": {"type": "object", "required": ["$ref"]},
            "then": _build_graph_reference_schema(),
            "else": inline_schema,
        }
    if isinstance(expected_type, type) and is_dataclass(expected_type):
        field_types = get_type_hints(expected_type)
        serialized_fields = [
            field for field in fields(expected_type) if field.init
        ]
        properties = {
            field.name: _build_graph_value_schema(
                field_types.get(field.name, field.type),
                definition_names,
            )
            for field in serialized_fields
        }
        return {
            "type": "object",
            "additionalProperties": False,
            "required": list(properties),
            "properties": properties,
        }
    return _build_schema(expected_type)


def _build_graph_reference_schema() -> JsonSchema:
    """Return the JSON shape of one object-table reference."""
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["$ref"],
        "properties": {
            "$ref": {
                "type": "string",
                "pattern": r"^#/objects/[^/~]+$",
            },
        },
    }


def _build_graph_record_schema(
    serializable_type: type[Serializable],
    definition_names: Mapping[type[Serializable], str],
) -> JsonSchema:
    """Build the object-table record schema for one concrete class."""
    serialized_fields = serializable_type._serialized_field_types()
    properties = {
        field_name: _build_graph_value_schema(field_type, definition_names)
        for field_name, field_type in serialized_fields.items()
    }
    constructor_parameters = serializable_type._constructor_parameters()
    schema: JsonSchema = {
        "type": "object",
        "additionalProperties": serializable_type._accepts_extra_fields(),
        "required": [
            "__class__",
            "__module__",
            *properties,
        ],
        "properties": {
            "__class__": {"const": serializable_type.__name__},
            "__module__": {"const": serializable_type.__module__},
            **properties,
        },
    }
    constructor_only_parameters = _constructor_only_parameters(
        constructor_parameters,
        serialized_fields,
    )
    if constructor_only_parameters:
        schema["propertyNames"] = {
            "not": {"enum": constructor_only_parameters},
        }
    return schema


def _graph_serializable_types(expected_type: Any) -> list[type[Serializable]]:
    """Return every concrete Serializable record reachable from a root type."""
    result: list[type[Serializable]] = []
    visited: set[Any] = set()

    def collect(declared_type: Any) -> None:
        if declared_type in visited:
            return
        visited.add(declared_type)

        origin = get_origin(declared_type)
        if origin in (list, dict, Mapping, Union, UnionType):
            for argument in get_args(declared_type):
                if argument is not str:
                    collect(argument)
            return

        if isinstance(declared_type, type) and issubclass(
            declared_type,
            Serializable,
        ):
            concrete_types = (
                _concrete_serializable_types(declared_type)
                if _is_abstract_serializable(declared_type)
                else [declared_type]
            )
            for concrete_type in concrete_types:
                if concrete_type not in result:
                    result.append(concrete_type)
                for field_type in concrete_type._serialized_field_types().values():
                    collect(field_type)
            return

        if isinstance(declared_type, type) and is_dataclass(declared_type):
            for field_type in get_type_hints(declared_type).values():
                collect(field_type)

    collect(expected_type)
    return result


def _add_constructor_defaults(
    constructor_parameters: Mapping[str, inspect.Parameter],
    properties: Mapping[str, JsonSchema],
) -> None:
    """Add compatible constructor defaults as schema examples."""
    for field_name, field_schema in properties.items():
        parameter = constructor_parameters.get(field_name)
        if parameter is None or parameter.default is inspect.Parameter.empty:
            continue
        if _schema_accepts_default(field_schema, parameter.default):
            field_schema["default"] = parameter.default


def _schema_accepts_default(schema: Mapping[str, Any], value: Any) -> bool:
    """Return whether a JSON-compatible default matches a field schema."""
    return not json_schema_errors(dict(schema), value)


def _constructor_only_parameters(
    constructor_parameters: Mapping[str, inspect.Parameter],
    serialized_fields: Mapping[str, Any],
) -> list[str]:
    """Return explicit constructor parameters excluded from serialization."""
    return sorted(
        parameter_name
        for parameter_name, parameter in constructor_parameters.items()
        if (
            parameter_name not in serialized_fields
            and parameter_name != "self"
            and parameter.kind
            not in (
                inspect.Parameter.VAR_POSITIONAL,
                inspect.Parameter.VAR_KEYWORD,
            )
        )
    )


def _concrete_serializable_types(
    declared_type: type[Serializable],
) -> list[type[Serializable]]:
    """Return concrete implementations owned by the declaration's package."""
    package_name = declared_type.__module__.partition(".")[0]

    def is_supported_implementation(candidate: type[Serializable]) -> bool:
        return (
            not _is_abstract_serializable(candidate)
            and candidate.__module__.partition(".")[0] == package_name
        )

    allowed_types = {
        candidate
        for candidate in declared_type._known_serializable_types()
        if is_supported_implementation(candidate)
    }
    if not allowed_types:
        raise TypeError(
            f"{declared_type.__name__} has no concrete Serializable "
            "implementation."
        )
    return sorted(
        allowed_types,
        key=lambda subclass: (
            subclass.__module__,
            subclass.__qualname__,
        ),
    )


def _is_abstract_serializable(
    serializable_type: type[Serializable],
) -> bool:
    """Return whether a Serializable is a declaration, not a file value."""
    return (
        inspect.isabstract(serializable_type)
        or ABC in serializable_type.__bases__
    )


def json_file_type_name(expected_type: Any) -> str:
    """Validate and describe a Serializable or list declaration."""
    if get_origin(expected_type) is list:
        item_types = get_args(expected_type)
        if len(item_types) != 1:
            raise TypeError("JsonFile list declarations require one item type.")
        return f"list[{json_file_type_name(item_types[0])}]"
    if isinstance(expected_type, type) and issubclass(
        expected_type,
        Serializable,
    ):
        return expected_type.__name__
    raise TypeError(
        "JsonFile.value_type must be a Serializable class or list thereof."
    )


def _json_path(parts: Iterable[str | int]) -> str:
    """Return a readable path to a value inside a JSON document."""
    path = "$"
    for part in parts:
        if isinstance(part, int):
            path += f"[{part}]"
        else:
            path += f".{part}"
    return path


def _schema_error_message(error: Any) -> str:
    """Return a schema-provided message or the validator's default."""
    if isinstance(error.schema, Mapping):
        return error.schema.get("x-error-message", error.message)
    return error.message
