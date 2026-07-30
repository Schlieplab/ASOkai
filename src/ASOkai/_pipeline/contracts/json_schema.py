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
import sys
from collections.abc import Iterable, Mapping, Sequence
from types import NoneType, SimpleNamespace, UnionType
from typing import (
    Any,
    ClassVar,
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


def validate_json_data(
    expected_type: Any,
    json_data: JsonData,
) -> None:
    """Raise one error containing every schema issue in a JSON document."""
    expected_type_name = json_file_type_name(expected_type)
    schema = build_json_schema(expected_type)
    validator = validator_for(schema)(schema)
    errors = sorted(
        validator.iter_errors(json_data),
        key=lambda error: (
            tuple(str(part) for part in error.absolute_path),
            error.message,
        ),
    )
    if not errors:
        return

    details = "\n".join(
        f"- {_json_path(error.absolute_path)}: {error.message}"
        for error in errors
    )
    raise ValueError(
        f"JSON does not match the {expected_type_name} schema:\n{details}"
    )


def _build_schema(
    expected_type: Any,
    *,
    allow_subclasses: bool = False,
) -> JsonSchema:
    """Return the JSON representation of one annotated Python type."""
    origin = get_origin(expected_type)
    arguments = get_args(expected_type)

    if origin is list:
        if len(arguments) != 1:
            raise TypeError("JSON list annotations require one item type.")
        return {
            "type": "array",
            "items": _build_schema(
                arguments[0],
                allow_subclasses=True,
            ),
        }

    if origin in (dict, Mapping):
        if len(arguments) != 2 or arguments[0] is not str:
            raise TypeError(
                "JSON mapping annotations must have string keys and one "
                "value type."
            )
        return {
            "type": "object",
            "additionalProperties": _build_schema(
                arguments[1],
                allow_subclasses=True,
            ),
        }

    if origin is Literal:
        return {"enum": list(arguments)}

    if origin in (Union, UnionType):
        return {
            "anyOf": [
                _build_schema(
                    argument,
                    allow_subclasses=allow_subclasses,
                )
                for argument in arguments
            ]
        }

    scalar_types = {
        str: "string",
        int: "integer",
        float: "number",
        bool: "boolean",
        NoneType: "null",
        Seq: "string",
    }
    if expected_type in scalar_types:
        return {"type": scalar_types[expected_type]}

    if isinstance(expected_type, type) and issubclass(
        expected_type,
        Serializable,
    ):
        allowed_types = (
            _concrete_serializable_types(expected_type)
            if allow_subclasses or inspect.isabstract(expected_type)
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


def _build_object_schema(
    serializable_type: type[Serializable],
) -> JsonSchema:
    """Build the object schema for one concrete Serializable class."""
    serialized_fields = _serialized_fields(serializable_type)
    properties = {
        field_name: _build_schema(
            field_type,
            allow_subclasses=True,
        )
        for field_name, field_type in serialized_fields.items()
    }
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


def _serialized_fields(
    serializable_type: type[Serializable],
) -> dict[str, Any]:
    """Collect serialized field annotations from the full class hierarchy."""
    serialized_fields: dict[str, Any] = {}
    attribute_serializers = serializable_type._attribute_serializers
    serialized_private_fields = attribute_serializers.keys()
    for class_in_hierarchy in reversed(serializable_type.__mro__):
        for field_name, field_type in _declared_field_types(
            class_in_hierarchy,
            serialized_private_fields=serialized_private_fields,
        ).items():
            serializer = attribute_serializers.get(field_name)
            if serializer is None:
                serialized_fields[field_name] = field_type
                continue

            serialized_name, _, flatten = serializer
            if flatten:
                for flattened_class in reversed(field_type.__mro__):
                    serialized_fields.update(
                        _declared_field_types(flattened_class)
                    )
                continue
            serialized_fields[serialized_name] = field_type
    return serialized_fields


def _declared_field_types(
    declaring_class: type[Any],
    *,
    serialized_private_fields: Iterable[str] = (),
) -> dict[str, Any]:
    """Resolve the relevant fields declared directly by one class."""
    serialized_private_field_names = set(serialized_private_fields)
    annotations = {
        field_name: annotation
        for field_name, annotation in declaring_class.__dict__.get(
            "__annotations__",
            {},
        ).items()
        if (
            not field_name.startswith("_")
            or field_name in serialized_private_field_names
        )
    }
    if not annotations:
        return {}

    annotation_holder = SimpleNamespace(__annotations__=annotations)
    resolved_fields = get_type_hints(
        annotation_holder,
        globalns=vars(sys.modules[declaring_class.__module__]),
        localns=dict(vars(declaring_class)),
    )
    return {
        field_name: field_type
        for field_name, field_type in resolved_fields.items()
        if get_origin(field_type) is not ClassVar
    }


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
    """Return every concrete Serializable allowed by a declaration."""
    allowed_types: set[type[Serializable]] = set()
    if not inspect.isabstract(declared_type):
        allowed_types.add(declared_type)
    subclasses_to_check = list(declared_type.__subclasses__())
    while subclasses_to_check:
        subclass = subclasses_to_check.pop()
        subclasses_to_check.extend(subclass.__subclasses__())
        if not inspect.isabstract(subclass):
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
