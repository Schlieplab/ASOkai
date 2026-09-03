#!/usr/bin/env python
"""
Filename: tests/unit/test_aso.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Tests for antisense oligonucleotide domain classes.
License: LGPL-3.0-or-later
"""

import inspect

from Bio.Seq import Seq
import pytest

from ASOkai.Antisense import ASO, AntisenseTherapeutic, Oligonucleotide, siRNA
from ASOkai.Biochemistry import MechanismOfAction


class ExampleMechanism(MechanismOfAction):
    pass


def make_mechanism():
    return ExampleMechanism(name="RNA degradation")


def test_aso_combines_oligonucleotide_and_therapeutic_contracts():
    assert issubclass(ASO, Oligonucleotide)
    assert issubclass(ASO, AntisenseTherapeutic)


def test_antisense_therapeutic_is_abstract():
    assert inspect.isabstract(AntisenseTherapeutic)


def test_oligonucleotide_requires_a_sequence():
    with pytest.raises(ValueError, match="sequence cannot be empty"):
        Oligonucleotide(sequence=Seq(""))


def test_aso_is_its_own_antisense_strand():
    aso = ASO(
        id="aso-1",
        sequence=Seq("ATGC"),
        mechanism=make_mechanism(),
    )

    assert aso.antisense_strand is aso
    assert aso.sequence == Seq("ATGC")


def test_sirna_sequence_is_the_antisense_sequence():
    antisense = Oligonucleotide(
        sequence=Seq("ATGC"),
    )
    sense = Oligonucleotide(
        sequence=Seq("GCAT"),
    )
    sirna = siRNA(
        id="sirna-1",
        antisense_strand=antisense,
        sense_strand=sense,
        mechanism=make_mechanism(),
    )

    assert sirna.sequence == antisense.sequence
    assert sirna.sense_strand.sequence == sense.sequence


def test_sirna_serialization_roundtrip():
    sirna = siRNA(
        id="sirna-1",
        antisense_strand=Oligonucleotide(
            sequence=Seq("ATGC"),
        ),
        sense_strand=Oligonucleotide(
            sequence=Seq("GCAT"),
        ),
        mechanism=make_mechanism(),
    )

    data = sirna.to_dict()
    reconstructed = siRNA.from_dict(data)

    assert "antisense_strand" in data
    assert "sense_strand" in data
    assert "_antisense_strand" not in data
    assert "_sense_strand" not in data
    assert "id" not in data["antisense_strand"]
    assert "id" not in data["sense_strand"]
    assert isinstance(reconstructed, siRNA)
    assert reconstructed.sequence == sirna.sequence
    assert reconstructed.sense_strand.sequence == sirna.sense_strand.sequence
    assert isinstance(reconstructed.mechanism, ExampleMechanism)
