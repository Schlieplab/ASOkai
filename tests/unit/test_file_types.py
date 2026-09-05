#!/usr/bin/env python
"""
Filename: tests/unit/test_file_types.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Tests for pipeline file-format contracts.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

import json
from typing import Any, cast

import pytest

from ASOkai.Utils import Serializable
from ASOkai._pipeline.contracts.file_types import (
    CsvFile,
    FileType,
    JsonFile,
    KffFile,
)


def test_opaque_file_type_keeps_inputs_as_paths(tmp_path):
    path = tmp_path / "input.bin"

    assert FileType().read(path) == path
    assert FileType().validate(path) is None


def test_kff_file_keeps_inputs_as_paths_without_loading_the_index(tmp_path):
    path = tmp_path / "index.kff"
    path.write_bytes(b"KFF\x01index-dataKFF")

    assert KffFile().read(path) == path


def test_kff_file_read_does_not_repeat_contract_validation(tmp_path):
    path = tmp_path / "external.kff"
    path.write_bytes(b"not-a-kff-file")

    assert KffFile().read(path) == path


@pytest.mark.parametrize(
    "content",
    [
        b"KF",
        b"not-a-kff-file",
        b"KFFmissing-footer",
    ],
)
def test_kff_file_rejects_missing_framing_markers(tmp_path, content):
    path = tmp_path / "index.kff"
    path.write_bytes(content)

    with pytest.raises(ValueError, match="Invalid KFF file"):
        KffFile().validate(path)


def test_json_file_reads_and_writes_generic_json(tmp_path):
    file_type = JsonFile()
    path = tmp_path / "result.json"
    value = {"name": "result", "values": [1, 2, 3]}

    file_type.write(path, value)

    assert file_type.read(path) == value
    assert json.loads(path.read_text(encoding="utf-8")) == value


def test_typed_json_file_uses_serializable_annotations():
    class Data(Serializable):
        count: int

        def __init__(self, count):
            self.count = count
            super().__init__()

    file_type = JsonFile(Data)

    assert json.loads(file_type.dumps(Data(1)))["count"] == 1
    with pytest.raises(ValueError, match=r"\$.count"):
        file_type.dumps(Data("not-an-integer"))
    with pytest.raises(TypeError, match="requires Data"):
        file_type.dumps(cast(Any, "not-a-Data"))


def test_json_file_validation_does_not_construct_domain_values(
    tmp_path,
    monkeypatch,
):
    class Data(Serializable):
        value: int

        def __init__(self, value):
            self.value = value
            super().__init__()

    path = tmp_path / "result.json"
    file_type = JsonFile(Data)
    file_type.write(path, Data(1))

    def unexpected_from_dict(cls, data):
        raise AssertionError("validate() constructed a domain value")

    monkeypatch.setattr(Data, "from_dict", classmethod(unexpected_from_dict))

    file_type.validate(path)


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
