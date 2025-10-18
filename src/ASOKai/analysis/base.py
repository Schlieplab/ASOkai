#!/usr/bin/env python
"""
Filename: src/ASOKai/analysis/base.py
Author: Arash Ayat
Copyright: 2025, Alexander Schliep
Version: 0.1.0
Description: This file defines the base classes for different analysis types.
License: LGPL-3.0-or-later
"""
from abc import ABC, abstractmethod
from typing import Dict, Any

from ..targets import Target
from GenomeUtils.Genome import Genome


class AnalysisStep(ABC):
    """Abstract base class for an analysis step."""

    def __init__(self, **kwargs):
        self.kwargs = kwargs

    @abstractmethod
    def run(self) -> Any:
        """Executes the analysis step."""
        pass

    def __call__(self, *args, **kwargs):
        return self.run(*args, **kwargs)


class SiteWideAnalysis(AnalysisStep):
    """Base class for analyses that produce results for each site in a target."""

    def __init__(self, target: Target, **kwargs):
        super().__init__(**kwargs)
        self.target = target

    @abstractmethod
    def run(self) -> Dict[str, Dict[str, Any]]:
        """
        Executes the site-wide analysis.

        Returns:
            A dictionary of analysis results.
        """
        pass


class TargetWideAnalysis(AnalysisStep):
    """Base class for analyses that produce results for an entire target."""

    def __init__(self, target: Target, **kwargs):
        super().__init__(**kwargs)
        self.target = target

    @abstractmethod
    def run(self) -> Dict[str, Dict[str, Any]]:
        """
        Executes the target-wide analysis.

        Returns:
            A dictionary of analysis results.
        """
        pass


class GenomeWideAnalysis(AnalysisStep):
    """Base class for analyses that produce results for an entire genome."""

    def __init__(self, genome: Genome, target: Target = None, **kwargs):
        super().__init__(**kwargs)
        self.genome = genome
        self.target = target

    @abstractmethod
    def run(self) -> Dict[str, Dict[str, Any]]:
        """
        Executes the genome-wide analysis.

        Returns:
            A dictionary of analysis results.
        """
        pass
