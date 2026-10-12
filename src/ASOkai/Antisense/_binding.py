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
    """Two sequences and their antiparallel dot-bracket alignment.

    ``structure`` uses ``(`` for paired positions on the first strand,
    ``)`` for paired positions on the second, ``.`` for unpaired positions,
    and ``&`` between strands. IDs link independent bindings to their source
    records; an siRNA-owned binding has no endpoint IDs.
    """

    first_sequence: Seq
    second_sequence: Seq
    structure: str
    first_id: str | None
    second_id: str | None

    def __init__(
        self,
        first_sequence: Seq,
        second_sequence: Seq,
        structure: str,
        *,
        first_id: str | None = None,
        second_id: str | None = None,
    ):
        """Store a compact pairing structure for two 5'-to-3' sequences.

        Args:
            first_sequence: First sequence.
            second_sequence: Second sequence.
            structure: Two-strand dot-bracket structure.
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
        if not isinstance(structure, str):
            raise TypeError("Binding structure must be a string.")
        if "_" in structure:
            if "&" in structure:
                raise ValueError("Binding structure must have one strand separator.")
            structure = structure.replace("_", "&")
        self._parse_structure(structure, len(first_sequence), len(second_sequence))
        object.__setattr__(self, "first_sequence", first_sequence)
        object.__setattr__(self, "second_sequence", second_sequence)
        object.__setattr__(self, "structure", structure)
        object.__setattr__(self, "first_id", first_id)
        object.__setattr__(self, "second_id", second_id)

    @staticmethod
    def _parse_structure(
        structure: str, first_length: int, second_length: int
    ) -> tuple[BasePair, ...]:
        """Interpret an inter-strand dot-bracket structure as base pairs."""
        if structure.count("&") != 1:
            raise ValueError("Binding structure must have one strand separator.")
        first, second = structure.split("&")
        if len(first) != first_length or len(second) != second_length:
            raise ValueError("Binding structure lengths must match the sequences.")
        if any(char not in "(." for char in first) or any(
            char not in ")." for char in second
        ):
            raise ValueError("Binding structure has invalid dot-bracket positions.")
        open_indices = [index for index, char in enumerate(first) if char == "("]
        pairs: list[BasePair] = []
        for index, char in enumerate(second):
            if char == ")":
                if not open_indices:
                    raise ValueError("Binding structure has unmatched base pairs.")
                pairs.append(BasePair(open_indices.pop(), index))
        if open_indices:
            raise ValueError("Binding structure has unmatched base pairs.")
        if not pairs:
            raise ValueError("A binding requires at least one base pair.")
        return tuple(sorted(pairs, key=lambda pair: pair.first_index))

    @property
    def pairs(self) -> tuple[BasePair, ...]:
        """Interpret the compact structure as ordered antiparallel pairs."""
        return self._parse_structure(
            self.structure, len(self.first_sequence), len(self.second_sequence)
        )

    @classmethod
    def from_pairs(
        cls,
        first_sequence: Seq,
        second_sequence: Seq,
        pairs: Sequence[BasePair],
        *,
        first_id: str | None = None,
        second_id: str | None = None,
    ) -> "Binding":
        """Encode ordered antiparallel base-pair indices as dot-bracket."""
        if not isinstance(first_sequence, Seq) or not first_sequence:
            raise ValueError("Binding requires a non-empty first Seq.")
        if not isinstance(second_sequence, Seq) or not second_sequence:
            raise ValueError("Binding requires a non-empty second Seq.")
        if not isinstance(pairs, (list, tuple)) or not pairs:
            raise ValueError("A binding requires at least one base pair.")
        first = ["."] * len(first_sequence)
        second = ["."] * len(second_sequence)
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
            first[pair.first_index] = "("
            second[pair.second_index] = ")"
            previous_first = pair.first_index
            previous_second = pair.second_index
        return cls(
            first_sequence,
            second_sequence,
            "".join(first) + "&" + "".join(second),
            first_id=first_id,
            second_id=second_id,
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
            "(" * length + "&" + ")" * length,
            first_id=first_id,
            second_id=second_id,
        )
