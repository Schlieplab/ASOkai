#!/usr/bin/env python
"""
Filename: src/ASOkai/Analysis/_base.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Per-unit and batch execution models for analyses.
License: LGPL-3.0-or-later
"""
import gc
import logging
import multiprocessing
import sys
import threading
from abc import ABC, abstractmethod
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from typing import Any, ClassVar, final

from tqdm import tqdm

from ASOkai.Types import AnalysisUnitType

logger = logging.getLogger(__name__)

# A progress bar otherwise starts a monitor thread that outlives it, and a
# parent with a second thread cannot fork workers, so showing progress would
# silently cost every process-backed analysis its parallelism.
tqdm.monitor_interval = 0

# Forked workers inherit these objects; tasks send only index ranges.
_WORKER_ANALYSIS: "PerUnitAnalysis | None" = None
_WORKER_UNITS: list[Any] = []

# Keep the published objects stable for the entire process-backed run.
_WORKER_PUBLICATION = threading.Lock()


def _analyze_index_range(index_range: tuple[int, int]) -> list[Any]:
    """Analyze one half-open range of inherited units in a worker process."""
    analysis = _WORKER_ANALYSIS
    if analysis is None:
        raise RuntimeError("Worker process inherited no analysis to run.")
    results: list[Any] = []
    for index in range(*index_range):
        results.extend(analysis.analyze_unit(_WORKER_UNITS[index]))
    return results


class Analysis(ABC):
    """Base for analyses that produce results from biological units."""

    analysis_unit_type: ClassVar[AnalysisUnitType | None] = None

    @abstractmethod
    def run(self, units: Iterable[Any], *, n_workers: int = 1) -> list[Any]:
        """Analyze the supplied units and collect their results."""
        ...


class PerUnitAnalysis(Analysis):
    """Analyze each unit independently and return results in input order.

    One worker runs directly; multiple workers use threads by default. Set
    :attr:`uses_worker_processes` in a subclass to use forked processes on
    Linux when the parent has one Python thread and is not itself a
    multiprocessing worker. Other cases use threads. The parent runs one
    process-backed analysis at a time so each pool inherits the correct data.

    Forked workers inherit the analysis and units through copy-on-write
    memory. Tasks send only index ranges; results are serialized back to the
    parent and must be picklable. Analyses must treat context and units as
    read-only while workers run. Open database connections and other stateful
    handles in a worker before using them, rather than reusing inherited ones.
    """

    #: Prefer forked processes when supported; otherwise use threads.
    uses_worker_processes: ClassVar[bool] = False

    #: Units per process task, or None to derive a chunk size.
    worker_chunk_size: ClassVar[int | None] = None

    #: Target tasks per process when deriving a chunk size.
    target_tasks_per_worker: ClassVar[int] = 256

    #: Show a progress bar while running, on a terminal.
    show_progress: ClassVar[bool] = True

    @final
    def run(self, units: Iterable[Any], *, n_workers: int = 1) -> list[Any]:
        """Collect zero or more results per unit in input order."""
        if type(n_workers) is not int or n_workers < 1:
            raise ValueError("n_workers must be a positive integer.")
        analysis_units = list(units)
        if not analysis_units:
            return []
        with self._progress(len(analysis_units)) as progress:
            if n_workers == 1:
                logger.debug("%s: running sequentially", type(self).__name__)
                return self._collect(
                    ((1, self.analyze_unit(unit)) for unit in analysis_units),
                    progress,
                )
            if self.uses_worker_processes:
                reason = self._fork_unavailable_reason()
                if reason is None:
                    logger.debug(
                        "%s: using %d process workers", type(self).__name__, n_workers
                    )
                    return self._run_on_processes(analysis_units, n_workers, progress)
                logger.debug(
                    "%s: using %d thread workers (process workers unavailable: %s)",
                    type(self).__name__,
                    n_workers,
                    reason,
                )
            else:
                logger.debug(
                    "%s: using %d thread workers", type(self).__name__, n_workers
                )
            with ThreadPoolExecutor(max_workers=n_workers) as executor:
                return self._collect(
                    (
                        (1, unit_results)
                        for unit_results in executor.map(
                            self.analyze_unit, analysis_units
                        )
                    ),
                    progress,
                )

    def _progress(self, n_units: int) -> tqdm:
        """Return a progress bar over the units about to be analyzed."""
        return tqdm(
            total=n_units,
            desc=type(self).__name__,
            unit=self.analysis_unit_type or "unit",
            # None lets tqdm disable itself off a terminal, which keeps
            # carriage returns out of pipeline and CWL logs.
            disable=None if self.show_progress else True,
        )

    @staticmethod
    def _collect(
        analyzed: Iterable[tuple[int, Iterable[Any]]], progress: tqdm
    ) -> list[Any]:
        """Flatten results in input order, counting units as they finish."""
        results: list[Any] = []
        for n_units, unit_results in analyzed:
            results.extend(unit_results)
            progress.update(n_units)
        return results

    @staticmethod
    def _fork_unavailable_reason() -> str | None:
        """Explain why this process cannot use the fork worker pool."""
        if not sys.platform.startswith("linux"):
            return "fork workers are supported only on Linux"
        # Other Python threads may leave locks held in a forked child.
        if threading.active_count() != 1:
            return "the parent has multiple Python threads"
        # Pool children inherit the parent's held publication lock.
        if multiprocessing.parent_process() is not None:
            return "this is already a multiprocessing worker"
        return None

    def chunk_size(self, n_units: int, n_workers: int) -> int:
        """Return how many units each worker task receives."""
        if self.worker_chunk_size is None:
            return max(1, n_units // (n_workers * self.target_tasks_per_worker))
        if type(self.worker_chunk_size) is not int or self.worker_chunk_size < 1:
            raise ValueError("worker_chunk_size must be a positive integer.")
        return self.worker_chunk_size

    def _run_on_processes(
        self, analysis_units: list[Any], n_workers: int, progress: tqdm
    ) -> list[Any]:
        """Analyze units on forked workers that inherit them from this process."""
        global _WORKER_ANALYSIS, _WORKER_UNITS

        chunk_size = self.chunk_size(len(analysis_units), n_workers)
        index_ranges = [
            (start, min(start + chunk_size, len(analysis_units)))
            for start in range(0, len(analysis_units), chunk_size)
        ]
        with _WORKER_PUBLICATION:
            # Pool creation forks workers with the currently published objects.
            _WORKER_ANALYSIS, _WORKER_UNITS = self, analysis_units
            # Avoid GC writes to inherited pages without undoing a freeze
            # already present when this run started.
            owns_frozen_generation = gc.get_freeze_count() == 0
            if owns_frozen_generation:
                gc.freeze()
            try:
                context = multiprocessing.get_context("fork")
                with context.Pool(processes=n_workers) as pool:
                    # A task covers a whole range, so it advances the bar by
                    # every unit it analyzed rather than by one.
                    return self._collect(
                        (
                            (stop - start, chunk_results)
                            for (start, stop), chunk_results in zip(
                                index_ranges,
                                pool.imap(_analyze_index_range, index_ranges),
                            )
                        ),
                        progress,
                    )
            finally:
                if owns_frozen_generation:
                    gc.unfreeze()
                _WORKER_ANALYSIS, _WORKER_UNITS = None, []

    @abstractmethod
    def analyze_unit(self, unit: Any, /) -> Iterable[Any]:
        """Return zero or more results for one analysis unit."""
        ...


class BatchAnalysis(Analysis):
    """Pass the whole collection of units to one backend invocation."""

    @final
    def run(self, units: Iterable[Any], *, n_workers: int = 1) -> list[Any]:
        """Pass the collected units and worker count to the backend."""
        if type(n_workers) is not int or n_workers < 1:
            raise ValueError("n_workers must be a positive integer.")
        return list(self.analyze_batch(list(units), n_workers=n_workers))

    @abstractmethod
    def analyze_batch(
        self, units: list[Any], *, n_workers: int
    ) -> Iterable[Any]:
        """Return results using the supplied worker budget as needed."""
        ...
