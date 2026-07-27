#!/usr/bin/env python
"""
Filename: src/ASOkai/_pipeline/contracts/file_types.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Version: 0.1.1
Description: File-format contracts used by pipeline inputs and outputs.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

import csv
import io
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Generic, Mapping, Sequence, TypeAlias, TypeVar, cast

from ASOkai.Utils._serializer import Serializable
from ASOkai._pipeline.contracts.json_schemas import JSON_SCHEMAS


FileValueT = TypeVar("FileValueT")
JsonValueT = TypeVar("JsonValueT")
CsvScalar: TypeAlias = str | int | float | bool | None
CsvRow: TypeAlias = Mapping[str, CsvScalar]
CsvTable: TypeAlias = Sequence[CsvRow]


@dataclass(frozen=True)
class FileType(Generic[FileValueT]):
    """An opaque file whose step argument remains a filesystem path."""

    media_type: str = "application/octet-stream"

    def __post_init__(self) -> None:
        if type(self.media_type) is not str or not self.media_type.strip():
            raise ValueError("FileType.media_type must be a non-blank string.")

    def read(self, path: str | Path) -> FileValueT:
        """Return an opaque input as a path without interpreting its contents."""
        return cast(FileValueT, Path(path))

    def loads(
        self,
        content: str,
        *,
        source: str = "<string>",
    ) -> FileValueT:
        """Reject text decoding for an opaque file type."""
        raise TypeError(f"{type(self).__name__} does not decode text.")

    def dumps(self, value: FileValueT) -> str:
        """Reject text encoding for an opaque file type."""
        raise TypeError(f"{type(self).__name__} does not encode text.")

    def write(self, path: str | Path, value: FileValueT) -> None:
        """Reject direct writing for an opaque file type."""
        raise TypeError(f"{type(self).__name__} does not write values.")


@dataclass(frozen=True, init=False)
class JsonFile(FileType[JsonValueT], Generic[JsonValueT]):
    """A JSON file, optionally constrained to one Serializable domain class."""

    value_type: type[JsonValueT] | None

    def __init__(self, value_type: type[JsonValueT] | None = None) -> None:
        if value_type is not None and (
            not isinstance(value_type, type)
            or not issubclass(value_type, Serializable)
        ):
            raise TypeError(
                "JsonFile.value_type must inherit from Serializable."
            )
        object.__setattr__(self, "media_type", "application/json")
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
    ) -> JsonValueT:
        """Parse JSON and reconstruct a configured domain value when required."""
        try:
            payload = json.loads(
                content,
                object_pairs_hook=self._object_without_duplicate_keys,
                parse_constant=self._reject_non_finite_number,
            )
        except (json.JSONDecodeError, ValueError) as error:
            raise ValueError(f"Invalid JSON from {source}: {error}") from error

        value_type = self.value_type
        if value_type is None:
            return cast(JsonValueT, payload)
        domain_type = cast(type[Serializable], value_type)

        try:
            JSON_SCHEMAS.validate(domain_type, payload)
            value = domain_type.from_dict(payload)
            if type(value) is not domain_type:
                raise TypeError(
                    f"Deserializer returned {type(value).__name__}; expected "
                    f"{domain_type.__name__}."
                )
        except (ImportError, AttributeError, TypeError, ValueError) as error:
            raise ValueError(
                f"Invalid {domain_type.__name__} from {source}: {error}"
            ) from error
        return cast(JsonValueT, value)

    def dumps(self, value: JsonValueT) -> str:
        """Validate and serialize a JSON-compatible or domain value."""
        value_type = self.value_type
        if value_type is not None:
            domain_type = cast(type[Serializable], value_type)
            if type(value) is not domain_type:
                raise TypeError(
                    f"JsonFile requires {domain_type.__name__}; "
                    f"received {type(value).__name__}."
                )
            try:
                domain_value = cast(Serializable, value)
                payload = domain_value.to_dict()
                if not isinstance(payload, dict):
                    raise TypeError(
                        "Serializable.to_dict() must return a dictionary."
                    )
                JSON_SCHEMAS.validate(domain_type, payload)
            except (TypeError, ValueError) as error:
                raise ValueError(
                    f"Cannot serialize {domain_type.__name__}: {error}"
                ) from error
        else:
            payload = value

        try:
            return json.dumps(
                payload,
                indent=4,
                ensure_ascii=False,
                allow_nan=False,
            ) + "\n"
        except (TypeError, ValueError) as error:
            raise ValueError(f"Cannot serialize JSON: {error}") from error

    def read(self, path: str | Path) -> JsonValueT:
        """Read, parse, and validate a JSON file."""
        source = Path(path)
        return self.loads(
            source.read_text(encoding="utf-8"),
            source=str(source),
        )

    def write(self, path: str | Path, value: JsonValueT) -> None:
        """Validate and write a JSON file."""
        Path(path).write_text(
            self.dumps(value),
            encoding="utf-8",
        )


@dataclass(frozen=True, init=False)
class CsvFile(FileType[CsvTable]):
    """A tabular CSV file with optional fixed columns and scalar cells."""

    columns: tuple[str, ...] | None

    def __init__(self, columns: Sequence[str] | None = None) -> None:
        object.__setattr__(self, "media_type", "text/csv")
        object.__setattr__(
            self,
            "columns",
            None if columns is None else self._validate_columns(columns),
        )

    @staticmethod
    def _validate_columns(columns: Sequence[str]) -> tuple[str, ...]:
        """Return a validated, immutable CSV column declaration."""
        normalized = tuple(columns)
        if not normalized:
            raise ValueError("CsvFile requires at least one column.")
        if any(
            type(column) is not str or not column.strip()
            for column in normalized
        ):
            raise ValueError("CsvFile column names must be non-blank strings.")
        duplicates = sorted(
            {column for column in normalized if normalized.count(column) > 1}
        )
        if duplicates:
            raise ValueError(
                f"Duplicate CSV column name(s): {', '.join(duplicates)}."
            )
        return normalized

    def loads(
        self,
        content: str,
        *,
        source: str = "<string>",
    ) -> CsvTable:
        """Parse CSV while rejecting ambiguous headers and malformed rows."""
        reader = csv.DictReader(io.StringIO(content, newline=""))
        if reader.fieldnames is None:
            raise ValueError(f"CSV from {source} must contain a header row.")
        columns = self._validate_columns(reader.fieldnames)
        if self.columns is not None and columns != self.columns:
            raise ValueError(
                f"CSV from {source} has columns {columns!r}; "
                f"expected {self.columns!r}."
            )

        rows: list[dict[str, str]] = []
        for row_number, row in enumerate(reader, start=2):
            if None in row:
                raise ValueError(
                    f"CSV row {row_number} from {source} has extra values."
                )
            if any(value is None for value in row.values()):
                raise ValueError(
                    f"CSV row {row_number} from {source} is missing values."
                )
            rows.append(cast(dict[str, str], row))
        return rows

    def dumps(self, value: CsvTable) -> str:
        """Validate scalar rows and serialize them as CSV."""
        if isinstance(value, (str, bytes, Mapping)):
            raise TypeError("CsvFile requires a sequence of row mappings.")
        rows = list(value)
        if self.columns is not None:
            columns = self.columns
        elif rows:
            if not isinstance(rows[0], Mapping):
                raise TypeError("CSV row 1 must be a mapping.")
            columns = self._validate_columns(tuple(rows[0]))
        else:
            raise ValueError(
                "CsvFile without declared columns cannot serialize zero rows."
            )

        expected = set(columns)
        normalized_rows: list[dict[str, CsvScalar]] = []
        for row_number, row in enumerate(rows, start=1):
            if not isinstance(row, Mapping):
                raise TypeError(f"CSV row {row_number} must be a mapping.")
            actual = set(row)
            if actual != expected:
                missing = ", ".join(sorted(expected - actual)) or "none"
                unexpected = ", ".join(sorted(actual - expected)) or "none"
                raise ValueError(
                    f"CSV row {row_number} has inconsistent columns "
                    f"(missing: {missing}; unexpected: {unexpected})."
                )
            normalized: dict[str, CsvScalar] = {}
            for column in columns:
                cell = row[column]
                if type(cell) not in (str, int, float, bool, type(None)):
                    raise TypeError(
                        f"CSV row {row_number} column {column!r} must contain "
                        "a scalar value."
                    )
                if type(cell) is float and not math.isfinite(cell):
                    raise ValueError(
                        f"CSV row {row_number} column {column!r} must contain "
                        "a finite number."
                    )
                normalized[column] = cell
            normalized_rows.append(normalized)

        stream = io.StringIO(newline="")
        writer = csv.DictWriter(
            stream,
            fieldnames=list(columns),
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(normalized_rows)
        return stream.getvalue()

    def read(self, path: str | Path) -> CsvTable:
        """Read and validate a CSV file."""
        source = Path(path)
        return self.loads(
            source.read_text(encoding="utf-8"),
            source=str(source),
        )

    def write(self, path: str | Path, value: CsvTable) -> None:
        """Validate and write a CSV file."""
        Path(path).write_text(
            self.dumps(value),
            encoding="utf-8",
        )
