#!/usr/bin/env python
"""
Filename: src/ASOkai/_pipeline/contracts/file_types/csv.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Version: 0.1.1
Description: Contract for typed CSV tables.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

import csv
import io
import math
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Mapping, Sequence, TypeAlias, cast

from ASOkai._types import Scalar

from .base import FileType


CsvRow: TypeAlias = Mapping[str, Scalar]
CsvTable: TypeAlias = Sequence[CsvRow]


@dataclass(frozen=True, init=False)
class CsvFile(FileType):
    """A CSV table with explicitly typed index and data columns."""

    index: Mapping[str, type[Scalar]]
    columns: Mapping[str, type[Scalar]]

    def __init__(
        self,
        *,
        index: Mapping[str, type[Scalar]],
        columns: Mapping[str, type[Scalar]],
    ) -> None:
        object.__setattr__(self, "media_type", "text/csv")
        object.__setattr__(self, "format_name", "CSV")
        object.__setattr__(
            self,
            "index",
            self._validate_column_types("index", index),
        )
        object.__setattr__(
            self,
            "columns",
            self._validate_column_types("columns", columns),
        )
        overlap = set(self.index) & set(self.columns)
        if overlap:
            names = ", ".join(sorted(overlap))
            raise ValueError(
                f"CSV index and data columns overlap: {names}."
            )

    @staticmethod
    def _validate_column_types(
        group_name: str,
        column_types: Mapping[str, type[Scalar]],
    ) -> Mapping[str, type[Scalar]]:
        """Return one validated group of ordered CSV column types."""
        if not isinstance(column_types, Mapping):
            raise TypeError(
                f"CsvFile {group_name} must map column names to scalar types."
            )
        normalized = dict(column_types)
        if group_name == "columns" and not normalized:
            raise ValueError("CsvFile requires at least one data column.")
        if any(
            type(name) is not str or not name.strip()
            for name in normalized
        ):
            raise ValueError("CsvFile column names must be non-blank strings.")
        for name, value_type in normalized.items():
            if value_type not in (str, int, float, bool):
                raise TypeError(
                    f"CSV column {name!r} must declare one of "
                    "str, int, float, or bool."
                )
        return MappingProxyType(normalized)

    @property
    def field_types(self) -> dict[str, type[Scalar]]:
        """Return all CSV fields in their serialized order."""
        return {
            **self.index,
            **self.columns,
        }

    def _validate_header(
        self,
        fieldnames: Sequence[str],
        *,
        source: str,
    ) -> None:
        """Validate the names and order of a parsed CSV header."""
        actual = tuple(fieldnames)
        duplicates = sorted(
            {name for name in actual if actual.count(name) > 1}
        )
        if duplicates:
            raise ValueError(
                f"Duplicate CSV column name(s) from {source}: "
                f"{', '.join(duplicates)}."
            )

        expected = tuple(self.field_types)
        if actual != expected:
            raise ValueError(
                f"CSV from {source} has columns {actual!r}; "
                f"expected {expected!r}."
            )

    @staticmethod
    def _decode_cell(
        value: str,
        expected_type: type[Scalar],
        *,
        source: str,
        row_number: int,
        column_name: str,
    ) -> Scalar:
        """Decode one CSV cell using its declared scalar type."""
        try:
            if expected_type is str:
                return value
            if expected_type is int:
                return int(value)
            if expected_type is float:
                decoded_float = float(value)
                if not math.isfinite(decoded_float):
                    raise ValueError
                return decoded_float
            if expected_type is bool:
                if value == "true":
                    return True
                if value == "false":
                    return False
                raise ValueError
        except ValueError as error:
            raise ValueError(
                f"CSV row {row_number} column {column_name!r} from {source} "
                f"must be {expected_type.__name__}; received {value!r}."
            ) from error

        raise TypeError(
            f"CSV column {column_name!r} has unsupported type "
            f"{expected_type!r}."
        )

    @staticmethod
    def _encode_cell(
        value: Scalar,
        expected_type: type[Scalar],
        *,
        row_number: int,
        column_name: str,
    ) -> str:
        """Validate and encode one scalar CSV cell."""
        if type(value) is not expected_type:
            raise TypeError(
                f"CSV row {row_number} column {column_name!r} must be "
                f"{expected_type.__name__}; received {type(value).__name__}."
            )
        if expected_type is float and not math.isfinite(cast(float, value)):
            raise ValueError(
                f"CSV row {row_number} column {column_name!r} must be finite."
            )
        if expected_type is bool:
            return "true" if value else "false"
        return str(value)

    def _validate_index_values(
        self,
        rows: Sequence[CsvRow],
        *,
        source: str,
        first_row_number: int,
    ) -> None:
        """Require every declared index value to be complete and unique."""
        if not self.index:
            return

        seen: set[tuple[Scalar, ...]] = set()
        for offset, row in enumerate(rows):
            row_number = first_row_number + offset
            key = tuple(row[name] for name in self.index)
            if any(
                type(value) is str and not value.strip()
                for value in key
            ):
                raise ValueError(
                    f"CSV row {row_number} from {source} has a blank index."
                )
            if key in seen:
                raise ValueError(
                    f"CSV row {row_number} from {source} has duplicate "
                    f"index {key!r}."
                )
            seen.add(key)

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
        self._validate_header(reader.fieldnames, source=source)

        rows: list[dict[str, Scalar]] = []
        for row_number, row in enumerate(reader, start=2):
            if None in row:
                raise ValueError(
                    f"CSV row {row_number} from {source} has extra values."
                )
            if any(value is None for value in row.values()):
                raise ValueError(
                    f"CSV row {row_number} from {source} is missing values."
                )
            rows.append(
                {
                    name: self._decode_cell(
                        cast(str, row[name]),
                        value_type,
                        source=source,
                        row_number=row_number,
                        column_name=name,
                    )
                    for name, value_type in self.field_types.items()
                }
            )
        self._validate_index_values(
            rows,
            source=source,
            first_row_number=2,
        )
        return rows

    def dumps(self, value: CsvTable) -> str:
        """Validate typed rows and serialize them as CSV."""
        if isinstance(value, (str, bytes, Mapping)):
            raise TypeError("CsvFile requires a sequence of row mappings.")
        rows = list(value)
        field_types = self.field_types
        expected = set(field_types)
        normalized_rows: list[dict[str, Scalar]] = []
        encoded_rows: list[dict[str, str]] = []
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
            normalized: dict[str, Scalar] = {}
            encoded: dict[str, str] = {}
            for name, expected_type in field_types.items():
                cell = row[name]
                encoded[name] = self._encode_cell(
                    cell,
                    expected_type,
                    row_number=row_number,
                    column_name=name,
                )
                normalized[name] = cell
            normalized_rows.append(normalized)
            encoded_rows.append(encoded)

        self._validate_index_values(
            normalized_rows,
            source="the supplied rows",
            first_row_number=1,
        )

        stream = io.StringIO(newline="")
        writer = csv.DictWriter(
            stream,
            fieldnames=list(field_types),
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(encoded_rows)
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
