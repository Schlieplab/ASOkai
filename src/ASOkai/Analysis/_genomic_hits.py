#!/usr/bin/env python
"""
Filename: src/ASOkai/Analysis/_genomic_hits.py
Author: Kian Jalilian
Copyright: 2026, Alexander Schliep
Description: This file defines the GenomicHitsAnalysis class for counting the genomic hits of target sites.
License: LGPL-3.0-or-later
"""

from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import ClassVar

from ..Sites import GenomicSite, Site
from ..Types import AnalysisUnitType, Scalar
from ..Utils import Serializable
from ._base import BatchAnalysis


class SiteGenomicHits(Serializable):
    """The genomic sites at which one target site's sequence aligns."""

    site_id: str
    genomic_sites: list[GenomicSite]

    def __init__(
        self,
        site_id: str,
        genomic_sites: Sequence[GenomicSite],
    ) -> None:
        """Initialize the genomic hits of one target site.

        Args:
            site_id: ID of the target site whose sequence was searched.
            genomic_sites: Genomic sites at which the sequence occurs.
        """
        self.site_id = site_id
        self.genomic_sites = list(genomic_sites)


class GenomicHitsAnalysis(BatchAnalysis):
    """
    Counts the genomic sites at which each target site aligns.

    Available features:
        - **repeated_count**: The number of genomic sites at which the
          target-site sequence occurs.
    """

    analysis_unit_type: ClassVar[AnalysisUnitType] = "site"

    def __init__(self, alignments: Path) -> None:
        """Initialize a genomic-hits analysis.

        Args:
            alignments: SAM alignments of the target-site queries.
        """
        self.alignments = Path(alignments)
        self.site_hits: list[SiteGenomicHits] = []

    def analyze_batch(
        self,
        units: list[Site],
        *,
        n_threads: int,
    ) -> Iterable[dict[str, Scalar]]:
        """Count the genomic hits of every target site from its alignments.

        Also stores one ``SiteGenomicHits`` record per site in ``site_hits``.

        Returns:
            One row per site containing the site ID and ``repeated_count``.
        """
        # TODO: Parse self.alignments, group the aligned genomic sites by
        # target site, fill self.site_hits, and return one row per site.
        raise NotImplementedError(
            "GenomicHitsAnalysis.analyze_batch() is not implemented yet."
        )
