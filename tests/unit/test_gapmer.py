#!/usr/bin/env python
"""
Filename: tests/unit/test_gapmer.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Version: 0.1.1
Description: Tests for the Gapmer domain class.
License: LGPL-3.0-or-later
"""

import pytest
from Bio.Seq import Seq

from ASOkai.Antisense import ASO, Gapmer
from ASOkai.Biochemistry import RNaseH1Mechanism


def make_gapmer(layout: str = "3-10-3") -> Gapmer:
    return Gapmer(
        id="gapmer-1",
        sequence=Seq("A" * 16),
        mechanism=RNaseH1Mechanism(),
        layout=layout,
    )


def test_gapmer_stores_its_layout():
    gapmer = make_gapmer("3-6-3")

    assert isinstance(gapmer, ASO)
    assert gapmer.layout == "3-6-3"


@pytest.mark.parametrize("layout", ["3-0-3", "3--1-3", "3-10", "invalid"])
def test_gapmer_rejects_invalid_layouts(layout):
    with pytest.raises(ValueError, match="Gapmer layout"):
        make_gapmer(layout)


def test_gapmer_supports_asymmetric_layouts():
    gapmer = make_gapmer("3-10-5")

    assert gapmer.lengths == (3, 10, 5)
    assert gapmer.left_wing_length == 3
    assert gapmer.gap_length == 10
    assert gapmer.right_wing_length == 5


def test_gapmer_serialization_roundtrip():
    reconstructed = Gapmer.from_dict(make_gapmer("3-10-5").to_dict())

    assert isinstance(reconstructed, Gapmer)
    assert reconstructed.layout == "3-10-5"
    assert reconstructed.sequence == Seq("A" * 16)
    assert isinstance(reconstructed.mechanism, RNaseH1Mechanism)
