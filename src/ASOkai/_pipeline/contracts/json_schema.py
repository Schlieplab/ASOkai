#!/usr/bin/env python
"""
Filename: src/ASOkai/_pipeline/contracts/json_schema.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Version: 0.1.1
Description: Recursive JSON schemas for Serializable values.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

import inspect
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
_JSON_SCALAR_SCHEMA: JsonSchema = {
    "type": ["string", "number", "boolean", "null"],
}


def build_json_schema(expected_type: Any) -> JsonSchema:
    """Build a JSON schema recursively from Serializable annotations."""
    title = json_file_type_name(expected_type)
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": title,
        **_build_schema(expected_type),
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
            "examples": ["ACGT"],
        }

    if isinstance(expected_type, type) and is_dataclass(expected_type):
        return _build_dataclass_schema(expected_type)

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
    _add_constructor_defaults(serializable_type, properties)
    schema: JsonSchema = {
        "type": "object",
        "additionalProperties": (
            _JSON_SCALAR_SCHEMA
            if _accepts_extra_scalars(serializable_type)
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
        serializable_type,
        serialized_fields,
    )
    if constructor_only_parameters:
        schema["propertyNames"] = {
            "not": {"enum": constructor_only_parameters},
        }
    return schema


def _add_constructor_defaults(
    serializable_type: type[Serializable],
    properties: Mapping[str, JsonSchema],
) -> None:
    """Add compatible constructor defaults as schema examples."""
    parameters = inspect.signature(serializable_type.__init__).parameters
    for field_name, field_schema in properties.items():
        parameter = parameters.get(field_name)
        if parameter is None or parameter.default is inspect.Parameter.empty:
            continue
        if _schema_accepts_default(field_schema, parameter.default):
            field_schema["default"] = parameter.default


def _schema_accepts_default(schema: Mapping[str, Any], value: Any) -> bool:
    """Return whether a JSON-compatible default matches a field schema."""
    alternatives = schema.get("oneOf", schema.get("anyOf"))
    if isinstance(alternatives, list):
        return any(
            isinstance(alternative, Mapping)
            and _schema_accepts_default(alternative, value)
            for alternative in alternatives
        )
    if "const" in schema:
        return value == schema["const"]
    if isinstance(schema.get("enum"), list):
        return value in schema["enum"]

    declared_type = schema.get("type")
    accepted_types = {
        "null": value is None,
        "boolean": type(value) is bool,
        "integer": type(value) is int,
        "number": type(value) in (int, float) and type(value) is not bool,
        "string": type(value) is str,
        "array": type(value) is list,
        "object": type(value) is dict,
    }
    if isinstance(declared_type, str):
        return accepted_types.get(declared_type, False)
    if isinstance(declared_type, list):
        return any(accepted_types.get(item, False) for item in declared_type)
    return False


def _accepts_extra_scalars(
    serializable_type: type[Serializable],
) -> bool:
    """Return whether the constructor accepts arbitrary keyword values."""
    return any(
        parameter.kind is inspect.Parameter.VAR_KEYWORD
        for parameter in inspect.signature(
            serializable_type.__init__
        ).parameters.values()
    )


def _constructor_only_parameters(
    serializable_type: type[Serializable],
    serialized_fields: Mapping[str, Any],
) -> list[str]:
    """Return explicit constructor parameters excluded from serialization."""
    return sorted(
        parameter_name
        for parameter_name, parameter in inspect.signature(
            serializable_type.__init__
        ).parameters.items()
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

    allowed_types: set[type[Serializable]] = set()
    if is_supported_implementation(declared_type):
        allowed_types.add(declared_type)
    subclasses_to_check = list(declared_type.__subclasses__())
    while subclasses_to_check:
        subclass = subclasses_to_check.pop()
        subclasses_to_check.extend(subclass.__subclasses__())
        if is_supported_implementation(subclass):
            allowed_types.add(subclass)
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
