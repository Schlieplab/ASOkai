#!/usr/bin/env python
"""
Filename: src/ASOkai/Analysis/_base.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Per-unit and batch execution models for analyses.
License: LGPL-3.0-or-later
"""
from abc import ABC, abstractmethod
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from typing import Any, ClassVar

from ASOkai.Types import AnalysisUnitType


class Analysis(ABC):
    """Base for analyses that produce results from biological units."""

    analysis_unit_type: ClassVar[AnalysisUnitType | None] = None

    @abstractmethod
    def run(self, units: Iterable[Any], *, n_threads: int = 1) -> list[Any]:
        """Analyze the supplied units and collect their results."""
        ...


class PerUnitAnalysis(Analysis):
    """Analyze units independently, optionally using shared worker threads.

    Implementations must treat shared context and units as read-only while
    :meth:`run` is executing with more than one thread.
    """

    def run(self, units: Iterable[Any], *, n_threads: int = 1) -> list[Any]:
        """Collect zero or more results per unit in input order."""
        if type(n_threads) is not int or n_threads < 1:
            raise ValueError("n_threads must be a positive integer.")
        analysis_units = list(units)
        if not analysis_units:
            return []
        if n_threads == 1:
            results = map(self.analyze_unit, analysis_units)
            return [result for unit_results in results for result in unit_results]
        with ThreadPoolExecutor(max_workers=n_threads) as executor:
            results = executor.map(self.analyze_unit, analysis_units)
            return [result for unit_results in results for result in unit_results]

    @abstractmethod
    def analyze_unit(self, unit: Any) -> Iterable[Any]:
        """Return zero or more results for one analysis unit."""
        ...


class BatchAnalysis(Analysis):
    """Pass the whole collection of units to one backend invocation."""

    def run(self, units: Iterable[Any], *, n_threads: int = 1) -> list[Any]:
        """Pass the collected units and thread count to the backend."""
        if type(n_threads) is not int or n_threads < 1:
            raise ValueError("n_threads must be a positive integer.")
        return list(self.analyze_batch(list(units), n_threads=n_threads))

    @abstractmethod
    def analyze_batch(
        self, units: list[Any], *, n_threads: int
    ) -> Iterable[Any]:
        """Return results using the supplied thread budget as needed."""
        ...
