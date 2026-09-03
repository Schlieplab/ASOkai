#!/usr/bin/env python
"""
Filename: tests/unit/test_gapmer.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Tests for the Gapmer domain class.
License: LGPL-3.0-or-later
"""

import pytest
from Bio.Seq import Seq

from ASOkai.Antisense import ASO, Gapmer
from ASOkai.Biochemistry import RNaseH1Mechanism


def make_gapmer(
    left_wing_length: int = 3,
    gap_length: int = 10,
    right_wing_length: int = 3,
) -> Gapmer:
    return Gapmer(
        id="gapmer-1",
        sequence=Seq("A" * 16),
        mechanism=RNaseH1Mechanism(),
        left_wing_length=left_wing_length,
        gap_length=gap_length,
        right_wing_length=right_wing_length,
    )


def test_gapmer_stores_its_layout():
    gapmer = make_gapmer(3, 10, 3)

    assert isinstance(gapmer, ASO)
    assert gapmer.layout == "3-10-3"


@pytest.mark.parametrize("value", [True, 0, -1, 1.5, "3"])
@pytest.mark.parametrize(
    "field",
    ["left_wing_length", "gap_length", "right_wing_length"],
)
def test_gapmer_rejects_invalid_segment_lengths(field, value):
    lengths = {
        "left_wing_length": 3,
        "gap_length": 10,
        "right_wing_length": 3,
    }
    lengths[field] = value

    with pytest.raises(ValueError, match=rf"Gapmer {field}"):
        make_gapmer(**lengths)


def test_gapmer_supports_asymmetric_layouts():
    gapmer = make_gapmer(3, 8, 5)

    assert gapmer.lengths == (3, 8, 5)
    assert gapmer.left_wing_length == 3
    assert gapmer.gap_length == 8
    assert gapmer.right_wing_length == 5


def test_gapmer_requires_segments_to_cover_the_sequence():
    with pytest.raises(
        ValueError,
        match=r"sequence length \(16\); received 3",
    ):
        make_gapmer(1, 1, 1)


def test_gapmer_serialization_roundtrip():
    reconstructed = Gapmer.from_dict(make_gapmer(3, 8, 5).to_dict())

    assert isinstance(reconstructed, Gapmer)
    assert reconstructed.layout == "3-8-5"
    assert reconstructed.lengths == (3, 8, 5)
    assert reconstructed.sequence == Seq("A" * 16)
    assert isinstance(reconstructed.mechanism, RNaseH1Mechanism)
