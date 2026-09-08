#!/usr/bin/env python
"""
Filename: src/ASOkai/Analysis/_intrinsic_features.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: This file defines the IntrinsicFeaturesAnalysis class for analyzing intrinsic features of target sites.
License: LGPL-3.0-or-later
"""

from collections.abc import Iterable
from typing import ClassVar

from ..Sites import Site
from ..Types import Scalar
from ._base import SiteSpecificAnalysis


class IntrinsicFeaturesAnalysis(SiteSpecificAnalysis):
    """
    Analyzes intrinsic features for each target site.

    Available features:
        - **GC_content**: The proportion of Guanine (G) and Cytosine (C) bases (between 0 and 1).
        - **AT_content**: The proportion of Adenine (A) and Thymine (T) bases (between 0 and 1).
        - **T_count**: The count of Thymine (T) bases.
        - **CpG_count**: The total count of CpG dinucleotides (a Cytosine followed by a Guanine).
        - **T_content**: The proportion of Thymine (T) bases (between 0 and 1).
        - **CpG_content**: CpG count divided by sequence length (between 0 and 1).
    """

    supported_features: ClassVar[tuple[str, ...]] = (
        "GC_content",
        "AT_content",
        "T_count",
        "CpG_count",
        "T_content",
        "CpG_content",
    )

    def __init__(
        self,
        sites: Iterable[Site],
        features: Iterable[str] | None = None,
        n_threads: int = 1,
    ) -> None:
        """Initialize an intrinsic-feature analysis.

        Args:
            sites: Sites to analyze.
            features: Features to calculate. Defaults to every supported
                feature.
            n_threads: Maximum number of worker threads used by ``run``.

        Raises:
            ValueError: If an unknown feature is requested.
        """
        selected_features = list(
            self.supported_features if features is None else features
        )
        unknown_features = sorted(
            set(selected_features) - set(self.supported_features)
        )
        if unknown_features:
            formatted = ", ".join(repr(name) for name in unknown_features)
            raise ValueError(f"Unknown intrinsic features: {formatted}.")
        self.features = tuple(selected_features)
        super().__init__(sites, n_threads=n_threads)

    def analyze(self, site: Site) -> dict[str, Scalar]:
        """Calculate the selected intrinsic features for one site.

        Returns:
            A dictionary mapping feature names to values.
        """
        sequence = str(site.sequence).upper()
        sequence_length = len(sequence)
        denominator = sequence_length or 1
        g_count = sequence.count("G")
        c_count = sequence.count("C")
        a_count = sequence.count("A")
        t_count = sequence.count("T")
        cpg_count = sequence.count("CG")
        all_results: dict[str, Scalar] = {
            "GC_content": (g_count + c_count) / denominator,
            "AT_content": (a_count + t_count) / denominator,
            "T_count": t_count,
            "CpG_count": cpg_count,
            "T_content": t_count / denominator,
            "CpG_content": cpg_count / denominator,
        }
        return {
            feature: all_results[feature]
            for feature in self.supported_features
            if feature in self.features
        }
