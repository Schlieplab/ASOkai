#!/usr/bin/env python
"""
Filename: src/ASOkai/Antisense/_binding.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: This file defines sequence binding and its aligned base pairs.
License: LGPL-3.0-or-later
"""
from collections.abc import Sequence
from dataclasses import dataclass

from Bio.Seq import Seq

from ..Utils import Serializable


@dataclass(frozen=True)
class BasePair:
    """Zero-based indices into two sequences stored 5' to 3'."""

    first_index: int
    second_index: int

    def __post_init__(self) -> None:
        if (
            type(self.first_index) is not int
            or type(self.second_index) is not int
            or self.first_index < 0
            or self.second_index < 0
        ):
            raise ValueError("Base-pair indices must be non-negative integers.")


@dataclass(frozen=True, init=False)
class Binding(Serializable):
    """Two sequences and their antiparallel alignment.

    Paired positions are ordered by increasing ``first_index`` and decreasing
    ``second_index``. Unpaired positions allow overhangs and bulges. IDs link
    independent bindings to their source records; an siRNA-owned binding has
    no endpoint IDs.
    """

    first_sequence: Seq
    second_sequence: Seq
    pairs: tuple[BasePair, ...]
    first_id: str | None
    second_id: str | None

    def __init__(
        self,
        first_sequence: Seq,
        second_sequence: Seq,
        pairs: Sequence[BasePair],
        *,
        first_id: str | None = None,
        second_id: str | None = None,
    ):
        """Store a pairing map for two 5'-to-3' sequences.

        Args:
            first_sequence: First sequence.
            second_sequence: Second sequence.
            pairs: Aligned positions in antiparallel order.
            first_id: First source ID, if this binding is stored independently.
            second_id: Second source ID, if this binding is stored independently.
        """
        if not isinstance(first_sequence, Seq) or not first_sequence:
            raise ValueError("Binding requires a non-empty first Seq.")
        if not isinstance(second_sequence, Seq) or not second_sequence:
            raise ValueError("Binding requires a non-empty second Seq.")
        if (first_id is None) != (second_id is None):
            raise ValueError("Binding endpoint IDs must be supplied together.")
        if first_id is not None and (
            type(first_id) is not str
            or not first_id
            or type(second_id) is not str
            or not second_id
        ):
            raise ValueError("Binding endpoint IDs must be non-empty strings.")
        if not isinstance(pairs, (list, tuple)) or not pairs:
            raise ValueError("A binding requires at least one base pair.")
        previous_first = -1
        previous_second = len(second_sequence)
        for pair in pairs:
            if not isinstance(pair, BasePair):
                raise TypeError("Binding pairs must be BasePair values.")
            if (
                pair.first_index >= len(first_sequence)
                or pair.second_index >= len(second_sequence)
            ):
                raise ValueError("Base-pair index exceeds a sequence length.")
            if (
                pair.first_index <= previous_first
                or pair.second_index >= previous_second
            ):
                raise ValueError("Base pairs must follow antiparallel order.")
            previous_first = pair.first_index
            previous_second = pair.second_index
        object.__setattr__(self, "first_sequence", first_sequence)
        object.__setattr__(self, "second_sequence", second_sequence)
        object.__setattr__(self, "pairs", tuple(pairs))
        object.__setattr__(self, "first_id", first_id)
        object.__setattr__(self, "second_id", second_id)

    @classmethod
    def _serialized_field_types(cls) -> dict[str, object]:
        """Expose the immutable pairing tuple as a JSON array."""
        field_types = dict(super()._serialized_field_types())
        field_types["pairs"] = list[BasePair]
        return field_types

    def _serialize_attribute(self, attribute_name, value, *, graph=None):
        if attribute_name == "pairs":
            return {
                "pairs": [
                    self._serialize_value(pair, graph=graph)
                    for pair in value
                ]
            }
        return super()._serialize_attribute(
            attribute_name, value, graph=graph
        )

    @classmethod
    def from_complementary_sequences(
        cls,
        first_sequence: Seq,
        second_sequence: Seq,
        *,
        first_id: str | None = None,
        second_id: str | None = None,
    ) -> "Binding":
        """Pair every base of two reverse-complementary sequences."""
        if first_sequence.reverse_complement() != second_sequence:
            raise ValueError("Binding sequences must be reverse complements.")
        length = len(first_sequence)
        return cls(
            first_sequence,
            second_sequence,
            [BasePair(index, length - index - 1) for index in range(length)],
            first_id=first_id,
            second_id=second_id,
        )
