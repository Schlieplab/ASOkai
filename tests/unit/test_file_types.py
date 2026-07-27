#!/usr/bin/env python
"""Tests for pipeline file-format contracts."""

from __future__ import annotations

import json
from typing import Any, cast

import pytest

from ASOkai._pipeline.contracts.file_types import CsvFile, FileType, JsonFile


def test_opaque_file_type_keeps_inputs_as_paths(tmp_path):
    path = tmp_path / "input.bin"

    assert FileType().read(path) == path


def test_json_file_reads_and_writes_generic_json(tmp_path):
    file_type = JsonFile()
    path = tmp_path / "result.json"
    value = {"name": "result", "values": [1, 2, 3]}

    file_type.write(path, value)

    assert file_type.read(path) == value
    assert json.loads(path.read_text(encoding="utf-8")) == value


@pytest.mark.parametrize(
    "content",
    [
        '{"value": 1, "value": 2}',
        '{"value": NaN}',
    ],
)
def test_json_file_rejects_ambiguous_json(content):
    with pytest.raises(ValueError, match="Invalid JSON"):
        JsonFile().loads(content)


def test_csv_file_roundtrip_validates_columns_and_scalar_cells(tmp_path):
    file_type = CsvFile(("site_id", "score", "accepted"))
    path = tmp_path / "results.csv"
    rows = [
        {"site_id": "site-1", "score": 0.75, "accepted": True},
        {"site_id": "site-2", "score": 0.25, "accepted": False},
    ]

    file_type.write(path, rows)

    assert file_type.read(path) == [
        {"site_id": "site-1", "score": "0.75", "accepted": "True"},
        {"site_id": "site-2", "score": "0.25", "accepted": "False"},
    ]


def test_csv_file_rejects_inconsistent_columns():
    file_type = CsvFile(("site_id", "score"))

    with pytest.raises(ValueError, match="inconsistent columns"):
        file_type.dumps([{"site_id": "site-1"}])


def test_csv_file_rejects_non_scalar_cells():
    file_type = CsvFile(("site_id", "score"))

    with pytest.raises(TypeError, match="scalar value"):
        file_type.dumps(
            cast(
                Any,
                [{"site_id": "site-1", "score": {"nested": "value"}}],
            )
        )


def test_csv_file_rejects_duplicate_header_columns():
    with pytest.raises(ValueError, match="Duplicate CSV column"):
        CsvFile().loads("site_id,site_id\nsite-1,site-2\n")
