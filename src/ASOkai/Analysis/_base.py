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
from collections.abc import Iterable
from multiprocessing import get_context
from typing import ClassVar

from GenomeUtils.Genome import Genome

from ..Sites import Site
from ..Targets import TargetGene
from ..Types import Scalar


class Analysis(ABC):
    """Abstract base class for computational analysis logic."""

    scope_label: ClassVar[str | None] = None

    def __init__(
        self,
        sites: Iterable[Site],
        n_processes: int = 1,
    ) -> None:
        if type(n_processes) is not int or n_processes < 1:
            raise ValueError("n_processes must be a positive integer.")
        self.sites = list(sites)
        seen_site_ids: set[str] = set()
        for site in self.sites:
            if site.id in seen_site_ids:
                raise ValueError(f"Duplicate analysis site ID: {site.id!r}.")
            seen_site_ids.add(site.id)
        self.n_processes = n_processes

    def run(self) -> dict[str, dict[str, Scalar]]:
        """Execute this analysis over all configured sites."""
        if not self.sites:
            return {}
        if self.n_processes == 1:
            return dict(self._analyze_site(site) for site in self.sites)

        with get_context("spawn").Pool(processes=self.n_processes) as pool:
            return dict(pool.map(self._analyze_site, self.sites))

    def _analyze_site(self, site: Site) -> tuple[str, dict[str, Scalar]]:
        return site.id, self.analyze(site)

    @abstractmethod
    def analyze(self, site: Site) -> dict[str, Scalar]:
        """Analyze one site and return CSV-compatible scalar values."""
        ...

    def __call__(self) -> dict[str, dict[str, Scalar]]:
        """Execute this analysis over all configured sites."""
        return self.run()


class SiteSpecificAnalysis(Analysis):
    """Base class for analyses that produce value dictionaries per site."""

    scope_label: ClassVar[str | None] = "Site-specific"


class TargetSpecificAnalysis(Analysis):
    """Base class for analyses that produce results for an entire target."""

    scope_label: ClassVar[str | None] = "Target-specific"

    def __init__(
        self,
        target: TargetGene,
        sites: Iterable[Site],
        n_processes: int = 1,
    ) -> None:
        super().__init__(sites, n_processes=n_processes)
        self.target = target


class GenomeWideAnalysis(Analysis):
    """Base class for analyses that produce results for an entire genome."""

    scope_label: ClassVar[str | None] = "Genome-wide"

    def __init__(
        self,
        genome: Genome,
        target: TargetGene,
        sites: Iterable[Site],
        n_processes: int = 1,
    ) -> None:
        super().__init__(sites, n_processes=n_processes)
        self.genome = genome
        self.target = target
