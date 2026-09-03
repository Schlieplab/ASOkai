#!/usr/bin/env python
"""
Filename: tests/unit/test_intrinsic_features.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Tests for intrinsic target-site feature calculations.
License: LGPL-3.0-or-later
"""

from Bio.Seq import Seq
import pytest

from ASOkai.Analysis import IntrinsicFeaturesAnalysis
from ASOkai.Sites import Site


class FeatureSite(Site):
    def __init__(self, sequence: str, id: str = "site-1") -> None:
        super().__init__(id=id, sequence=Seq(sequence))

    def __repr__(self) -> str:
        return f"FeatureSite(id={self.id!r})"


@pytest.mark.parametrize("sequence", ["GCGT", "gcgt"])
def test_intrinsic_features_are_case_insensitive(sequence):
    site = FeatureSite(sequence)

    assert IntrinsicFeaturesAnalysis([site]).analyze(site) == {
        "GC_content": 0.75,
        "AT_content": 0.25,
        "T_count": 1,
        "CpG_count": 1,
        "T_content": 0.25,
        "CpG_content": 0.25,
    }


def test_intrinsic_features_include_ambiguous_bases_in_the_denominator():
    site = FeatureSite("GNCG")

    assert IntrinsicFeaturesAnalysis([site]).analyze(site) == {
        "GC_content": 0.75,
        "AT_content": 0.0,
        "T_count": 0,
        "CpG_count": 1,
        "T_content": 0.0,
        "CpG_content": 0.25,
    }


def test_intrinsic_features_count_repeated_cpg_dinucleotides():
    site = FeatureSite("CGCG")

    results = IntrinsicFeaturesAnalysis([site]).analyze(site)

    assert results["CpG_count"] == 2
    assert results["CpG_content"] == 0.5


def test_intrinsic_features_return_zero_for_an_empty_sequence():
    site = FeatureSite("")

    assert IntrinsicFeaturesAnalysis([site]).analyze(site) == {
        "GC_content": 0.0,
        "AT_content": 0.0,
        "T_count": 0,
        "CpG_count": 0,
        "T_content": 0.0,
        "CpG_content": 0.0,
    }


def test_intrinsic_features_copy_the_selected_features():
    site = FeatureSite("GCGT")
    features = ["GC_content"]
    analysis = IntrinsicFeaturesAnalysis([site], features=features)
    features.append("T_count")

    assert analysis.analyze(site) == {"GC_content": 0.75}


def test_intrinsic_features_reject_unknown_feature_names():
    site = FeatureSite("GCGT")

    with pytest.raises(
        ValueError,
        match="Unknown intrinsic features: 'GC_contnet'",
    ):
        IntrinsicFeaturesAnalysis([site], features=["GC_contnet"])
