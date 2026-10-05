#!/usr/bin/env python
"""
Filename: tests/unit/test_analysis_base.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Tests for per-unit and batch analysis execution.
License: LGPL-3.0-or-later
"""

from collections.abc import Iterable
from threading import Lock
from time import sleep
from typing import ClassVar

import pytest

from ASOkai.Analysis import Analysis, BatchAnalysis, PerUnitAnalysis
from ASOkai.Types import AnalysisUnitType, Scalar


class CountingAnalysis(PerUnitAnalysis):
    analysis_unit_type: ClassVar[AnalysisUnitType] = "site"

    def analyze_unit(self, unit: int) -> list[dict[str, Scalar]]:
        sleep((3 - unit) * 0.001)
        return [{"unit": unit, "hit": hit} for hit in range(unit)]


class ContextAnalysis(PerUnitAnalysis):
    analysis_unit_type: ClassVar[AnalysisUnitType] = "therapeutic"

    def __init__(self, context: object) -> None:
        self.context = context

    def analyze_unit(self, unit: str) -> list[dict[str, Scalar]]:
        return [{"unit": unit, "context_id": id(self.context)}]


class RecordingBatch(BatchAnalysis):
    analysis_unit_type: ClassVar[AnalysisUnitType] = "binding"

    def __init__(self) -> None:
        self.calls: list[tuple[list[int], int]] = []

    def analyze_batch(
        self,
        units: list[int],
        *,
        n_threads: int,
    ) -> Iterable[dict[str, Scalar]]:
        self.calls.append((units, n_threads))
        return [{"total": sum(units)}]


def test_per_unit_analysis_collects_zero_or_many_results_in_input_order():
    analysis = CountingAnalysis()

    assert isinstance(analysis, Analysis)
    expected = [
        {"unit": 1, "hit": 0},
        {"unit": 2, "hit": 0},
        {"unit": 2, "hit": 1},
    ]
    assert analysis.run(iter([0, 1, 2])) == expected
    assert analysis.run(iter([0, 1, 2]), n_threads=3) == expected
    assert analysis.run([], n_threads=2) == []


class TextAnalysis(PerUnitAnalysis):
    analysis_unit_type: ClassVar[AnalysisUnitType] = "site"

    def analyze_unit(self, unit: int) -> list[str]:
        return [f"{unit}:{index}" for index in range(unit)]


def test_per_unit_analysis_can_return_non_table_results():
    assert TextAnalysis().run([0, 2], n_threads=2) == ["2:0", "2:1"]


@pytest.mark.parametrize("n_threads", [True, False, 0, -1, 1.5, "2"])
def test_per_unit_analysis_rejects_invalid_thread_count(n_threads):
    with pytest.raises(ValueError, match="n_threads"):
        CountingAnalysis().run([1], n_threads=n_threads)


def test_per_unit_threads_share_unpicklable_constructor_context():
    context = Lock()
    analysis = ContextAnalysis(context)

    assert analysis.run(["a", "b"], n_threads=2) == [
        {"unit": "a", "context_id": id(context)},
        {"unit": "b", "context_id": id(context)},
    ]


def test_batch_receives_the_whole_collection_once_including_empty_input():
    analysis = RecordingBatch()

    assert analysis.run(iter([1, 2, 3]), n_threads=4) == [{"total": 6}]
    assert analysis.calls == [([1, 2, 3], 4)]
    assert analysis.run([]) == [{"total": 0}]
    assert analysis.calls == [([1, 2, 3], 4), ([], 1)]


class TextBatch(BatchAnalysis):
    analysis_unit_type: ClassVar[AnalysisUnitType] = "site"

    def analyze_batch(
        self, units: list[int], *, n_threads: int
    ) -> Iterable[str]:
        return [f"{n_threads}:{','.join(map(str, units))}"]


def test_batch_analysis_can_return_non_table_results():
    assert TextBatch().run([1, 2], n_threads=3) == ["3:1,2"]


@pytest.mark.parametrize("n_threads", [True, False, 0, -1, 1.5, "2"])
def test_batch_analysis_rejects_invalid_thread_count(n_threads):
    with pytest.raises(ValueError, match="n_threads"):
        RecordingBatch().run([1], n_threads=n_threads)
