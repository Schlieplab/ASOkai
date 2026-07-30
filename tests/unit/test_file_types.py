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


def test_csv_file_roundtrip_preserves_declared_scalar_types(tmp_path):
    file_type = CsvFile(
        index={"site_id": str},
        columns={
            "score": float,
            "accepted": bool,
        },
    )
    path = tmp_path / "results.csv"
    rows = [
        {"site_id": "site-1", "score": 0.75, "accepted": True},
        {"site_id": "site-2", "score": 0.25, "accepted": False},
    ]

    file_type.write(path, rows)

    assert path.read_text() == (
        "site_id,score,accepted\n"
        "site-1,0.75,true\n"
        "site-2,0.25,false\n"
    )
    assert file_type.read(path) == rows


def test_csv_file_rejects_inconsistent_columns():
    file_type = CsvFile(
        index={"site_id": str},
        columns={"score": float},
    )

    with pytest.raises(ValueError, match="inconsistent columns"):
        file_type.dumps([{"site_id": "site-1"}])


def test_csv_file_rejects_values_with_the_wrong_declared_type():
    file_type = CsvFile(
        index={"site_id": str},
        columns={"score": float},
    )

    with pytest.raises(TypeError, match="must be float; received dict"):
        file_type.dumps(
            cast(
                Any,
                [{"site_id": "site-1", "score": {"nested": "value"}}],
            )
        )


def test_csv_file_rejects_duplicate_header_columns():
    file_type = CsvFile(
        index={"site_id": str},
        columns={"score": float},
    )

    with pytest.raises(ValueError, match="Duplicate CSV column"):
        file_type.loads("site_id,score,score\nsite-1,0.5,0.6\n")


def test_csv_file_rejects_invalid_declared_column_types():
    with pytest.raises(TypeError, match="'details'.*str, int, float, or bool"):
        CsvFile(
            index={"site_id": str},
            columns=cast(Any, {"details": dict}),
        )


def test_csv_file_keeps_index_and_data_columns_separate():
    with pytest.raises(ValueError, match="overlap.*site_id"):
        CsvFile(
            index={"site_id": str},
            columns={
                "site_id": str,
                "score": float,
            },
        )


def test_csv_file_rejects_invalid_file_values_with_row_and_column():
    file_type = CsvFile(
        index={"site_id": str},
        columns={"score": float},
    )

    with pytest.raises(
        ValueError,
        match=r"row 2 column 'score'.*must be float.*'high'",
    ):
        file_type.loads("site_id,score\nsite-1,high\n")


@pytest.mark.parametrize(
    "rows",
    [
        [
            {"site_id": "site-1", "score": 0.5},
            {"site_id": "site-1", "score": 0.6},
        ],
        [
            {"site_id": "", "score": 0.5},
        ],
    ],
)
def test_csv_file_rejects_invalid_index_values(rows):
    file_type = CsvFile(
        index={"site_id": str},
        columns={"score": float},
    )

    with pytest.raises(ValueError, match="index"):
        file_type.dumps(rows)


def test_csv_file_validates_a_combined_index():
    file_type = CsvFile(
        index={
            "target_id": str,
            "site_id": str,
        },
        columns={"score": float},
    )
    rows = [
        {"target_id": "target-1", "site_id": "site-1", "score": 0.5},
        {"target_id": "target-1", "site_id": "site-2", "score": 0.6},
    ]

    assert file_type.loads(file_type.dumps(rows)) == rows
