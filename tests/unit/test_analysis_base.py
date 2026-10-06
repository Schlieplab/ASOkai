#!/usr/bin/env python
"""
Filename: tests/unit/test_analysis_base.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Tests for per-unit and batch analysis execution.
License: LGPL-3.0-or-later
"""

import gc
import logging
import sys
from collections.abc import Iterable
from multiprocessing import Barrier
from os import getpid
from pickle import dumps
from threading import Event, Lock, Thread
from time import sleep
from typing import ClassVar

import pytest

from ASOkai.Analysis import Analysis, BatchAnalysis, PerUnitAnalysis
from ASOkai.Analysis import _base
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
        n_workers: int,
    ) -> Iterable[dict[str, Scalar]]:
        self.calls.append((units, n_workers))
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
    assert analysis.run(iter([0, 1, 2]), n_workers=3) == expected
    assert analysis.run([], n_workers=2) == []


class TextAnalysis(PerUnitAnalysis):
    analysis_unit_type: ClassVar[AnalysisUnitType] = "site"

    def analyze_unit(self, unit: int) -> list[str]:
        return [f"{unit}:{index}" for index in range(unit)]


def test_per_unit_analysis_can_return_non_table_results():
    assert TextAnalysis().run([0, 2], n_workers=2) == ["2:0", "2:1"]


@pytest.mark.parametrize("n_workers", [True, False, 0, -1, 1.5, "2"])
def test_per_unit_analysis_rejects_invalid_worker_count(n_workers):
    with pytest.raises(ValueError, match="n_workers"):
        CountingAnalysis().run([1], n_workers=n_workers)


def test_per_unit_threads_share_unpicklable_constructor_context():
    context = Lock()
    analysis = ContextAnalysis(context)

    assert analysis.run(["a", "b"], n_workers=2) == [
        {"unit": "a", "context_id": id(context)},
        {"unit": "b", "context_id": id(context)},
    ]


def test_batch_receives_the_whole_collection_once_including_empty_input():
    analysis = RecordingBatch()

    assert analysis.run(iter([1, 2, 3]), n_workers=4) == [{"total": 6}]
    assert analysis.calls == [([1, 2, 3], 4)]
    assert analysis.run([]) == [{"total": 0}]
    assert analysis.calls == [([1, 2, 3], 4), ([], 1)]


class TextBatch(BatchAnalysis):
    analysis_unit_type: ClassVar[AnalysisUnitType] = "site"

    def analyze_batch(
        self, units: list[int], *, n_workers: int
    ) -> Iterable[str]:
        return [f"{n_workers}:{','.join(map(str, units))}"]


def test_batch_analysis_can_return_non_table_results():
    assert TextBatch().run([1, 2], n_workers=3) == ["3:1,2"]


@pytest.mark.parametrize("n_workers", [True, False, 0, -1, 1.5, "2"])
def test_batch_analysis_rejects_invalid_worker_count(n_workers):
    with pytest.raises(ValueError, match="n_workers"):
        RecordingBatch().run([1], n_workers=n_workers)


class Unpicklable:
    """A value that cannot cross a process boundary by serialization."""

    def __init__(self, value: int) -> None:
        self.value = value

    def __reduce__(self):
        raise TypeError("Unpicklable is intentionally not serializable.")


class ForkedAnalysis(PerUnitAnalysis):
    analysis_unit_type: ClassVar[AnalysisUnitType] = "site"
    uses_worker_processes: ClassVar[bool] = True

    def __init__(self, context: object) -> None:
        self.context = context

    def analyze_unit(self, unit: Unpicklable) -> list[dict[str, Scalar]]:
        return [{"value": unit.value, "pid": getpid()}]


requires_fork = pytest.mark.skipif(
    not sys.platform.startswith("linux"),
    reason="Worker processes inherit memory by forking, which is Linux only.",
)


def test_unpicklable_units_and_context_are_inherited_not_pickled():
    analysis = ForkedAnalysis(Lock())
    units = [Unpicklable(value) for value in range(4)]

    with pytest.raises(TypeError, match="intentionally not serializable"):
        dumps(units[0])
    with pytest.raises(TypeError, match="cannot pickle"):
        dumps(analysis)


@requires_fork
def test_worker_processes_analyze_unpicklable_units_off_the_main_process(caplog):
    units = [Unpicklable(value) for value in range(4)]

    with caplog.at_level(logging.DEBUG, logger="ASOkai.Analysis._base"):
        results = ForkedAnalysis(Lock()).run(units, n_workers=2)

    assert [result["value"] for result in results] == [0, 1, 2, 3]
    assert all(result["pid"] != getpid() for result in results)
    assert "ForkedAnalysis: using 2 process workers" in caplog.messages


@requires_fork
def test_worker_count_changes_neither_results_nor_their_order():
    units = [Unpicklable(value) for value in range(16)]
    analysis = ForkedAnalysis(Lock())

    one_worker = [result["value"] for result in analysis.run(units)]
    many_workers = [
        result["value"] for result in analysis.run(units, n_workers=4)
    ]

    assert one_worker == list(range(16)) == many_workers


@requires_fork
def test_published_worker_context_is_released_after_the_run():
    ForkedAnalysis(Lock()).run([Unpicklable(0)], n_workers=2)

    assert _base._WORKER_ANALYSIS is None
    assert _base._WORKER_UNITS == []


class FailingAnalysis(PerUnitAnalysis):
    analysis_unit_type: ClassVar[AnalysisUnitType] = "site"
    uses_worker_processes: ClassVar[bool] = True
    worker_chunk_size: ClassVar[int] = 1

    def analyze_unit(self, unit: int) -> list[dict[str, Scalar]]:
        if unit == 2:
            raise ValueError("unit is unusable")
        return [{"unit": unit}]


@requires_fork
@pytest.mark.parametrize("n_workers", [1, 2])
def test_worker_failure_preserves_exception_type(n_workers):
    with pytest.raises(ValueError, match="unit is unusable"):
        FailingAnalysis().run([0, 1, 2, 3], n_workers=n_workers)


def test_worker_processes_fall_back_to_threads_without_forking(monkeypatch):
    monkeypatch.setattr(
        ForkedAnalysis,
        "_fork_unavailable_reason",
        staticmethod(lambda: "test condition"),
    )
    units = [Unpicklable(value) for value in range(4)]

    results = ForkedAnalysis(Lock()).run(units, n_workers=2)

    assert [result["value"] for result in results] == [0, 1, 2, 3]
    assert all(result["pid"] == getpid() for result in results)


def test_fallback_and_sequential_backends_are_logged_only_at_debug(
    monkeypatch, caplog
):
    monkeypatch.setattr(
        ForkedAnalysis,
        "_fork_unavailable_reason",
        staticmethod(lambda: "test condition"),
    )
    analysis = ForkedAnalysis(Lock())
    units = [Unpicklable(0)]

    analysis.run(units)
    analysis.run(units, n_workers=2)
    assert not caplog.records

    with caplog.at_level(logging.DEBUG, logger="ASOkai.Analysis._base"):
        analysis.run(units)
        analysis.run(units, n_workers=2)

    assert "ForkedAnalysis: running sequentially" in caplog.messages
    assert (
        "ForkedAnalysis: using 2 thread workers "
        "(process workers unavailable: test condition)"
    ) in caplog.messages


def test_thread_worker_failure_preserves_exception_type(monkeypatch):
    monkeypatch.setattr(
        FailingAnalysis,
        "_fork_unavailable_reason",
        staticmethod(lambda: "test condition"),
    )

    with pytest.raises(ValueError, match="unit is unusable"):
        FailingAnalysis().run([0, 1, 2, 3], n_workers=2)


@pytest.mark.parametrize(
    ("n_units", "n_workers", "expected"),
    [(1_000, 4, 1), (45_676, 4, 22), (36_000_000, 64, 1_098)],
)
def test_derived_chunk_size_bounds_dispatch_without_starving_workers(
    n_units, n_workers, expected
):
    assert ForkedAnalysis(None).chunk_size(n_units, n_workers) == expected


def test_declared_chunk_size_overrides_the_derived_one():
    assert FailingAnalysis().chunk_size(36_000_000, 64) == 1


@pytest.mark.parametrize("chunk_size", [True, 0, -1, 1.5, "2"])
def test_per_unit_analysis_rejects_invalid_chunk_size(chunk_size, monkeypatch):
    monkeypatch.setattr(ForkedAnalysis, "worker_chunk_size", chunk_size)

    with pytest.raises(ValueError, match="worker_chunk_size"):
        ForkedAnalysis(None).chunk_size(10, 2)


class PairedForkedAnalysis(PerUnitAnalysis):
    """Analyze units only in pairs, so one worker alone cannot finish."""

    analysis_unit_type: ClassVar[AnalysisUnitType] = "site"
    uses_worker_processes: ClassVar[bool] = True
    worker_chunk_size: ClassVar[int] = 1

    def __init__(self, n_workers: int) -> None:
        # Inherited by the forked workers, like every other unit of context.
        self.barrier = Barrier(n_workers)

    def analyze_unit(self, unit: int) -> list[dict[str, Scalar]]:
        self.barrier.wait(timeout=30)
        return [{"unit": unit, "pid": getpid()}]


@requires_fork
def test_every_worker_process_receives_part_of_the_work():
    # Each unit waits for a unit in another worker, so this completes only
    # if the work really was distributed, and raises rather than hanging.
    results = PairedForkedAnalysis(2).run(list(range(8)), n_workers=2)

    assert [result["unit"] for result in results] == list(range(8))
    assert len({result["pid"] for result in results}) == 2


@requires_fork
def test_run_leaves_a_freeze_made_by_the_caller_intact():
    gc.freeze()
    try:
        ForkedAnalysis(Lock()).run([Unpicklable(0)], n_workers=2)

        assert gc.get_freeze_count() > 0
    finally:
        gc.unfreeze()


@requires_fork
def test_run_leaves_the_frozen_generation_empty_when_it_started_empty():
    assert gc.get_freeze_count() == 0

    ForkedAnalysis(Lock()).run([Unpicklable(0)], n_workers=2)

    assert gc.get_freeze_count() == 0


@requires_fork
def test_a_multithreaded_parent_falls_back_to_worker_threads():
    # Forking would copy only this thread and leave the other's locks held.
    idle = Event()
    sentinel = Thread(target=idle.wait)
    sentinel.start()
    try:
        results = ForkedAnalysis(Lock()).run(
            [Unpicklable(value) for value in range(4)], n_workers=2
        )
    finally:
        idle.set()
        sentinel.join()

    assert [result["value"] for result in results] == [0, 1, 2, 3]
    assert all(result["pid"] == getpid() for result in results)


@requires_fork
def test_a_nested_analysis_inside_a_worker_falls_back_to_worker_threads(
    monkeypatch,
):
    # A worker inherits the publication lock held, so it must not fork again.
    monkeypatch.setattr(_base.multiprocessing, "parent_process", lambda: object())

    results = ForkedAnalysis(Lock()).run(
        [Unpicklable(value) for value in range(4)], n_workers=2
    )

    assert [result["value"] for result in results] == [0, 1, 2, 3]
    assert all(result["pid"] == getpid() for result in results)
