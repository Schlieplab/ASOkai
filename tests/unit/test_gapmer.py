#!/usr/bin/env python
"""Tests for gapmer chemistry and RNase-H1 candidate generation."""

import pytest

from ASOkai.Antisense import ASOCandidateGenerator
from ASOkai.Biochemistry import (
    GapmerChemistry,
    RNaseH1Mechanism,
)


def test_gapmer_stores_its_layout():
    chemistry = GapmerChemistry(layout="3-6-3")

    assert chemistry.id == "gapmer-3-6-3"


@pytest.mark.parametrize("layout", ["3-0-3", "3--1-3", "3-10", "invalid"])
def test_gapmer_rejects_invalid_layouts(layout):
    with pytest.raises(ValueError, match="Gapmer layout"):
        GapmerChemistry(layout=layout)


def test_gapmer_supports_asymmetric_layouts():
    chemistry = GapmerChemistry(layout="3-10-5")

    assert chemistry.lengths == (3, 10, 5)
    assert chemistry.left_wing_length == 3
    assert chemistry.gap_length == 10
    assert chemistry.right_wing_length == 5


def test_gapmer_serialization_roundtrip():
    reconstructed = GapmerChemistry.from_dict(
        GapmerChemistry(layout="3-10-5").to_dict()
    )

    assert isinstance(reconstructed, GapmerChemistry)
    assert reconstructed.layout == "3-10-5"
    assert set(reconstructed.to_dict()) == {"__class__", "__module__", "layout"}


def test_gapmer_and_rnase_h1_create_an_aso_generator():
    chemistry = GapmerChemistry(layout="3-10-3")
    mechanism = RNaseH1Mechanism()
    generator = ASOCandidateGenerator(chemistry=chemistry, mechanism=mechanism)

    assert isinstance(chemistry, GapmerChemistry)
    assert isinstance(mechanism, RNaseH1Mechanism)
    assert isinstance(generator, ASOCandidateGenerator)
