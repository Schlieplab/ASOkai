#!/usr/bin/env python
"""
Filename: src/ASOkai/_pipeline/contracts/json_schemas.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Version: 0.1.1
Description: JSON schemas used by typed pipeline files.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping, Sequence
from typing import Any, TypeAlias

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from ASOkai.Targets._target_gene import TargetGene
from ASOkai.Utils._serializer import Serializable


JsonValue: TypeAlias = (
    str
    | int
    | float
    | bool
    | None
    | Mapping[str, "JsonValue"]
    | Sequence["JsonValue"]
)
JsonSchema: TypeAlias = Mapping[str, Any]


class JsonSchemaRegistry:
    """Store and apply the JSON schema for each serialized domain type."""

    def __init__(self) -> None:
        self._validators: dict[
            type[Serializable],
            Draft202012Validator,
        ] = {}

    def register(
        self,
        value_type: type[Serializable],
        schema: JsonSchema,
    ) -> None:
        """Register one valid Draft 2020-12 schema for a domain type."""
        if value_type in self._validators:
            raise ValueError(
                f"A JSON schema is already registered for "
                f"{value_type.__module__}.{value_type.__name__}."
            )
        Draft202012Validator.check_schema(schema)
        self._validators[value_type] = Draft202012Validator(schema)

    def validate(
        self,
        value_type: type[Serializable],
        document: JsonValue,
    ) -> None:
        """Raise one error containing every schema issue in a JSON document."""
        validator = self._validators.get(value_type)
        if validator is None:
            raise ValueError(
                f"No JSON schema is registered for "
                f"{value_type.__module__}.{value_type.__name__}."
            )

        errors = sorted(
            (
                relevant_error
                for error in validator.iter_errors(document)
                for relevant_error in _relevant_schema_errors(error)
            ),
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
            f"JSON does not match the {value_type.__name__} schema:\n{details}"
        )


def _relevant_schema_errors(
    error: ValidationError,
) -> Iterator[ValidationError]:
    """Avoid reporting every rejected alternative of a union schema."""
    if not error.context:
        yield error
        return
    if error.validator not in {"oneOf", "anyOf"}:
        for nested_error in error.context:
            yield from _relevant_schema_errors(nested_error)
        return

    errors_by_alternative: dict[object, list[ValidationError]] = {}
    for nested_error in error.context:
        schema_path = iter(nested_error.relative_schema_path)
        alternative = next(schema_path, None)
        errors_by_alternative.setdefault(alternative, []).append(nested_error)

    closest_alternative = min(
        errors_by_alternative.values(),
        key=len,
    )
    for nested_error in closest_alternative:
        yield from _relevant_schema_errors(nested_error)


def _json_path(parts: Iterable[str | int]) -> str:
    """Return a readable path to a value inside a JSON document."""
    path = "$"
    for part in parts:
        if isinstance(part, int):
            path += f"[{part}]"
        else:
            path += f".{part}"
    return path


_NON_BLANK_STRING: JsonSchema = {
    "type": "string",
    "pattern": r"\S",
}

_SEQUENCE_STRING: JsonSchema = {
    "type": "string",
    "pattern": r"^\S+$",
}

TARGET_GENE_JSON_SCHEMA: JsonSchema = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "urn:asokai:schema:target-gene:1",
    "type": "object",
    "additionalProperties": False,
    "required": [
        "__class__",
        "__module__",
        "sequence",
        "id",
        "sites",
        "name",
        "chr",
        "start",
        "end",
        "strand",
    ],
    "properties": {
        "__class__": {"const": "TargetGene"},
        "__module__": {"const": "ASOkai.Targets._target_gene"},
        "sequence": _SEQUENCE_STRING,
        "id": _NON_BLANK_STRING,
        "sites": {
            "type": "object",
            "propertyNames": _NON_BLANK_STRING,
            "additionalProperties": {
                "oneOf": [
                    {"$ref": "#/$defs/genomicSite"},
                    {"$ref": "#/$defs/transcriptSite"},
                ]
            },
        },
        "name": _NON_BLANK_STRING,
        "chr": _NON_BLANK_STRING,
        "start": {"type": "integer", "minimum": 1},
        "end": {"type": "integer", "minimum": 1},
        "strand": {"enum": ["+", "-"]},
    },
    "$defs": {
        "genomicSite": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "__class__",
                "__module__",
                "id",
                "sequence",
                "chr",
                "start",
                "end",
                "strand",
            ],
            "properties": {
                "__class__": {"const": "GenomicSite"},
                "__module__": {"const": "ASOkai.Sites._genomic_site"},
                "id": _NON_BLANK_STRING,
                "sequence": _SEQUENCE_STRING,
                "chr": _NON_BLANK_STRING,
                "start": {"type": "integer", "minimum": 1},
                "end": {"type": "integer", "minimum": 1},
                "strand": {"enum": ["+", "-"]},
            },
        },
        "transcriptSite": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "__class__",
                "__module__",
                "transcript_id",
                "id",
                "t_start",
                "t_end",
                "sequence",
            ],
            "properties": {
                "__class__": {"const": "TranscriptSite"},
                "__module__": {"const": "ASOkai.Sites._transcript_site"},
                "transcript_id": _NON_BLANK_STRING,
                "id": _NON_BLANK_STRING,
                "t_start": {"type": "integer", "minimum": 0},
                "t_end": {"type": "integer", "minimum": 1},
                "sequence": _SEQUENCE_STRING,
            },
        },
    },
}


JSON_SCHEMAS = JsonSchemaRegistry()
JSON_SCHEMAS.register(TargetGene, TARGET_GENE_JSON_SCHEMA)
