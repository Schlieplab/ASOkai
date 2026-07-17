#!/usr/bin/env python
"""
Filename: src/ASOkai/Analysis/_intrinsic_features.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Version: 0.1.1
Description: This file defines the IntrinsicFeaturesAnalysis class for analyzing intrinsic features of target sites.
License: LGPL-3.0-or-later
"""
from typing import Any

from ._base import SiteSpecificAnalysis


class IntrinsicFeaturesAnalysis(SiteSpecificAnalysis):
    """
    Analyzes intrinsic features for each target site.

    Available features:
        - GC_content: The proportion of Guanine (G) and Cytosine (C) bases (between 0 and 1).
        - AT_content: The proportion of Adenine (A) and Thymine (T) bases (between 0 and 1).
        - T_count: The count of Thymine (T) bases.
        - CpG_count: The total count of CpG dinucleotides (a Cytosine followed by a Guanine).
        - T_content: The proportion of Thymine (T) bases (between 0 and 1).
        - CpG_content: The proportion of CpG dinucleotides (between 0 and 1).
    """

    def __init__(self, sites: list, features: list[str] | None = None, **kwargs):
        """
        Initializes the IntrinsicFeaturesAnalysis object.
        
        Args:
            sites: The sites to analyze.
            features: The features to analyze, defaults to all features.
            kwargs: Additional keyword arguments.
        """
        if features is None:
            features = [
                "GC_content",
                "AT_content",
                "T_count",
                "CpG_count",
                "T_content",
                "CpG_content",
            ]
        self.features: list[str] = features
        super().__init__(sites, **kwargs)

    def analyze(self, site) -> dict[str, Any]:
        """
        Calculates intrinsic features for one site.

        Returns:
            A dictionary mapping feature names to values.
        """
        sequence = str(site.sequence or "")
        seq_len = len(sequence) if sequence else 0
        results: dict[str, Any] = {}

        if "GC_content" in self.features:
            GC_content = sum(map(sequence.count, "GC")) / seq_len if seq_len > 0 else 0
            results["GC_content"] = GC_content

        if "AT_content" in self.features:
            AT_content = sum(map(sequence.count, "AT")) / seq_len if seq_len > 0 else 0
            results["AT_content"] = AT_content

        if "T_count" in self.features:
            T_count = sequence.count("T")
            results["T_count"] = T_count
            
        if "T_content" in self.features:
            T_content = sequence.count("T") / seq_len if seq_len > 0 else 0
            results["T_content"] = T_content

        if "CpG_count" in self.features:
            CpG_count = sequence.count("CG")
            results["CpG_count"] = CpG_count
            
        if "CpG_content" in self.features:
            CpG_content = sequence.count("CG") / seq_len if seq_len > 0 else 0
            results["CpG_content"] = CpG_content

        return results
