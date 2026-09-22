#!/usr/bin/env python
"""
Filename: src/ASOkai/_pipeline/contracts/file_types/json.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Contract for JSON files.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast, get_args, get_origin

from ASOkai.Utils._serializer import (
    Serializable,
    _deserialize_graph,
    _serialize_graph,
    _validate_graph,
)
from ASOkai._pipeline.contracts.json_schema import (
    json_file_type_name,
    validate_json_data,
    validate_json_graph_data,
)

from .base import FileType


def _validate_python_value(
    expected_type: Any,
    value: object,
    *,
    path: str = "$",
) -> None:
    """Validate the Python shape declared by a typed JsonFile."""
    if get_origin(expected_type) is list:
        if type(value) is not list:
            raise TypeError(
                f"JsonFile requires {json_file_type_name(expected_type)} "
                f"at {path}; received {type(value).__name__}."
            )
        expected_item_type = get_args(expected_type)[0]
        for index, item in enumerate(value):
            _validate_python_value(
                expected_item_type,
                item,
                path=f"{path}[{index}]",
            )
        return

    expected_type_name = json_file_type_name(expected_type)
    if not isinstance(value, Serializable):
        raise TypeError(
            f"JsonFile requires {expected_type_name} at {path}; "
            f"received {type(value).__name__}."
        )


def _from_json_data(
    expected_type: Any,
    json_data: object,
) -> Any:
    """Reconstruct domain values from the earlier inline representation."""
    if get_origin(expected_type) is list:
        expected_item_type = get_args(expected_type)[0]
        return [
            _from_json_data(expected_item_type, item)
            for item in cast(list[object], json_data)
        ]

    serializable_type = cast(type[Serializable], expected_type)
    return serializable_type.from_dict(cast(dict[str, Any], json_data))


def _is_graph_document(json_data: object) -> bool:
    """Return whether parsed JSON uses the Serializable graph envelope."""
    return isinstance(json_data, dict) and set(json_data) == {"root", "objects"}


@dataclass(frozen=True, init=False)
class JsonFile(FileType):
    """A JSON file optionally constrained to domain values or a domain list."""

    value_type: Any

    def __init__(
        self,
        value_type: Any = None,
    ) -> None:
        if value_type is not None:
            json_file_type_name(value_type)
        object.__setattr__(self, "media_type", "application/json")
        object.__setattr__(self, "format_name", "JSON")
        object.__setattr__(self, "value_type", value_type)

    @staticmethod
    def _object_without_duplicate_keys(
        pairs: list[tuple[str, Any]],
    ) -> dict[str, Any]:
        """Build a JSON object while rejecting ambiguous duplicate keys."""
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"Duplicate JSON key: {key!r}.")
            result[key] = value
        return result

    @staticmethod
    def _reject_non_finite_number(value: str) -> None:
        """Reject NaN and infinities, which are not valid JSON numbers."""
        raise ValueError(f"Non-finite JSON number: {value}.")

    def loads(
        self,
        content: str,
        *,
        source: str = "<string>",
    ) -> Any:
        """Parse, validate, and decode JSON content."""
        json_data = self._validated_json_data(content, source=source)
        expected_type = self.value_type
        if expected_type is None:
            return json_data
        expected_type_name = json_file_type_name(expected_type)

        try:
            if _is_graph_document(json_data):
                return _deserialize_graph(
                    cast(dict[str, Any], json_data),
                    expected_type,
                )
            return _from_json_data(expected_type, json_data)
        except (ImportError, AttributeError, TypeError, ValueError) as error:
            raise ValueError(
                f"Invalid {expected_type_name} from {source}: {error}"
            ) from error

    def _validated_json_data(
        self,
        content: str,
        *,
        source: str,
    ) -> Any:
        """Parse and validate serialized JSON without constructing domain values."""
        try:
            json_data = json.loads(
                content,
                object_pairs_hook=self._object_without_duplicate_keys,
                parse_constant=self._reject_non_finite_number,
            )
        except (json.JSONDecodeError, ValueError) as error:
            raise ValueError(f"Invalid JSON from {source}: {error}") from error

        expected_type = self.value_type
        if expected_type is None:
            return json_data
        expected_type_name = json_file_type_name(expected_type)

        try:
            if _is_graph_document(json_data):
                validate_json_graph_data(expected_type, json_data)
                _validate_graph(cast(dict[str, Any], json_data), expected_type)
            else:
                validate_json_data(expected_type, json_data)
        except (ImportError, AttributeError, TypeError, ValueError) as error:
            raise ValueError(
                f"Invalid {expected_type_name} from {source}: {error}"
            ) from error
        return json_data

    def dumps(self, value: Any) -> str:
        """Validate and serialize a JSON-compatible or domain value."""
        expected_type = self.value_type
        if expected_type is not None:
            expected_type_name = json_file_type_name(expected_type)
            try:
                _validate_python_value(expected_type, value)
                json_data = _serialize_graph(value)
                validate_json_graph_data(expected_type, json_data)
                _validate_graph(json_data, expected_type)
            except ValueError as error:
                raise ValueError(
                    f"Cannot serialize {expected_type_name}: {error}"
                ) from error
        else:
            json_data = value

        try:
            return json.dumps(
                json_data,
                indent=4,
                ensure_ascii=False,
                allow_nan=False,
            ) + "\n"
        except (TypeError, ValueError) as error:
            raise ValueError(f"Cannot serialize JSON: {error}") from error

    def read(self, path: str | Path) -> Any:
        """Read and decode a validated JSON file."""
        source = Path(path)
        return self.loads(
            source.read_text(encoding="utf-8"),
            source=str(source),
        )

    def validate(self, path: str | Path) -> None:
        """Validate JSON syntax and its configured serialized-data contract."""
        source = Path(path)
        self._validated_json_data(
            source.read_text(encoding="utf-8"),
            source=str(source),
        )

    def write(self, path: str | Path, value: Any) -> None:
        """Validate and write a JSON file."""
        Path(path).write_text(
            self.dumps(value),
            encoding="utf-8",
        )
