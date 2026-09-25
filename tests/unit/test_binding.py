#!/usr/bin/env python
"""
Filename: tests/unit/test_binding.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Tests for aligned sequence bindings.
License: LGPL-3.0-or-later
"""

from dataclasses import FrozenInstanceError

from Bio.Seq import Seq
import pytest

from ASOkai.Antisense import BasePair, Binding


def test_binding_serializes_two_sequences_and_their_pairing():
    binding = Binding.from_complementary_sequences(
        Seq("GCAT"), Seq("ATGC"), first_id="aso:1", second_id="site:1"
    )

    data = binding.to_dict()
    reconstructed = Binding.from_dict(data)

    assert data == {
        "__class__": "Binding",
        "__module__": "ASOkai.Antisense._binding",
        "first_sequence": "GCAT",
        "second_sequence": "ATGC",
        "pairs": [
            {"first_index": 0, "second_index": 3},
            {"first_index": 1, "second_index": 2},
            {"first_index": 2, "second_index": 1},
            {"first_index": 3, "second_index": 0},
        ],
        "first_id": "aso:1",
        "second_id": "site:1",
    }
    assert isinstance(reconstructed, Binding)
    assert reconstructed.first_sequence == binding.first_sequence
    assert reconstructed.second_sequence == binding.second_sequence
    assert reconstructed.first_id == binding.first_id
    assert reconstructed.second_id == binding.second_id
    assert reconstructed.pairs == binding.pairs


def test_binding_allows_unpaired_positions_and_mismatches():
    binding = Binding(
        Seq("ACGTA"),
        Seq("ATCT"),
        [BasePair(0, 3), BasePair(2, 2), BasePair(3, 0)],
    )

    assert binding.first_id is None
    assert binding.second_id is None
    assert [pair.first_index for pair in binding.pairs] == [0, 2, 3]
    assert Binding.from_dict(binding.to_dict()).pairs == binding.pairs


def test_binding_cannot_be_changed_after_validation():
    input_pairs = [BasePair(0, 1), BasePair(1, 0)]
    binding = Binding(Seq("AT"), Seq("AT"), input_pairs)
    input_pairs.clear()

    assert binding.pairs == (BasePair(0, 1), BasePair(1, 0))
    with pytest.raises(FrozenInstanceError):
        binding.first_sequence = Seq("GC")
    with pytest.raises(FrozenInstanceError):
        binding.pairs = ()
    with pytest.raises(AttributeError):
        binding.pairs.append(BasePair(0, 0))


@pytest.mark.parametrize(
    "first_id, second_id",
    [("aso:1", None), (None, "site:1"), ("", "site:1"), ("aso:1", "")],
)
def test_binding_requires_both_nonempty_endpoint_ids_or_neither(
    first_id, second_id
):
    with pytest.raises(ValueError, match="endpoint IDs"):
        Binding(
            Seq("A"),
            Seq("T"),
            [BasePair(0, 0)],
            first_id=first_id,
            second_id=second_id,
        )


@pytest.mark.parametrize(
    "pairs, message",
    [
        ([], "at least one"),
        ([BasePair(0, 4)], "exceeds"),
        ([BasePair(0, 2), BasePair(0, 1)], "antiparallel"),
        ([BasePair(0, 2), BasePair(1, 3)], "antiparallel"),
    ],
)
def test_binding_rejects_invalid_pairing(pairs, message):
    with pytest.raises(ValueError, match=message):
        Binding(
            Seq("ACGT"),
            Seq("TGCA"),
            pairs,
        )


def test_complementary_constructor_rejects_noncomplementary_strands():
    with pytest.raises(ValueError, match="reverse complements"):
        Binding.from_complementary_sequences(
            Seq("AAAA"),
            Seq("AAAA"),
        )
