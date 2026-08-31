#!/usr/bin/env python
"""
Filename: src/ASOkai/Analysis/_base.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Version: 0.1.1
Description: This file defines the base classes for different analysis types.
License: LGPL-3.0-or-later
"""
from abc import ABC, abstractmethod
from multiprocessing import get_context
from typing import ClassVar

from ..Types import Scalar
from ..Targets import TargetGene
from GenomeUtils.Genome import Genome


class Analysis(ABC):
    """Abstract base class for computational analysis logic."""

    scope_label: ClassVar[str | None] = None

    def __init__(self, sites: list, n_processes: int = 1, **kwargs):
        if n_processes < 1:
            raise ValueError("n_processes must be >= 1.")
        self.sites = list(sites)
        self.n_processes = n_processes
        self.kwargs = kwargs

    def run(self) -> dict[str, dict[str, Scalar]]:
        """Execute this analysis over all configured sites."""
        if self.n_processes == 1:
            return dict(self._analyze_site(site) for site in self.sites)

        with get_context("spawn").Pool(processes=self.n_processes) as pool:
            return dict(pool.map(self._analyze_site, self.sites))

    def _analyze_site(self, site) -> tuple[str, dict[str, Scalar]]:
        return site.id, self.analyze(site)

    @abstractmethod
    def analyze(self, site) -> dict[str, Scalar]:
        """Analyze one site and return CSV-compatible scalar values."""
        ...

    def __call__(self, *args, **kwargs):
        return self.run(*args, **kwargs)


class SiteSpecificAnalysis(Analysis):
    """Base class for analyses that produce value dictionaries per site."""

    scope_label: ClassVar[str | None] = "Site-specific"


class TargetSpecificAnalysis(Analysis):
    """Base class for analyses that produce results for an entire target."""

    scope_label: ClassVar[str | None] = "Target-specific"

    def __init__(
        self,
        target: TargetGene,
        sites: list,
        n_processes: int = 1,
        **kwargs,
    ):
        super().__init__(sites, n_processes=n_processes, **kwargs)
        self.target = target


class GenomeWideAnalysis(Analysis):
    """Base class for analyses that produce results for an entire genome."""

    scope_label: ClassVar[str | None] = "Genome-wide"

    def __init__(
        self,
        genome: Genome,
        target: TargetGene,
        sites: list,
        n_processes: int = 1,
        **kwargs,
    ):
        super().__init__(sites, n_processes=n_processes, **kwargs)
        self.genome = genome
        self.target = target
