#!/usr/bin/env python
"""
Filename: src/ASOkai/Antisense/_gapmer.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Version: 0.1.1
Description: This file defines the Gapmer class.
License: LGPL-3.0-or-later
"""

from Bio.Seq import Seq

from ..Biochemistry import MechanismOfAction
from ._aso import ASO


class Gapmer(ASO):
    """An ASO with a wing-gap-wing design."""

    left_wing_length: int
    gap_length: int
    right_wing_length: int

    def __init__(
        self,
        id: str,
        sequence: Seq,
        mechanism: MechanismOfAction,
        left_wing_length: int,
        gap_length: int,
        right_wing_length: int,
        **kwargs,
    ):
        """Initialize a gapmer.

        Args:
            id: Unique therapeutic identifier.
            sequence: Antisense-strand sequence in the 5' to 3' direction.
            mechanism: Mechanism through which the gapmer acts.
            left_wing_length: Number of nucleotides in the left wing.
            gap_length: Number of nucleotides in the central gap.
            right_wing_length: Number of nucleotides in the right wing.
            kwargs: Additional scalar values retained during serialization.
        """
        self.left_wing_length = _positive_length(
            "left_wing_length",
            left_wing_length,
        )
        self.gap_length = _positive_length("gap_length", gap_length)
        self.right_wing_length = _positive_length(
            "right_wing_length",
            right_wing_length,
        )
        super().__init__(
            id=id,
            sequence=sequence,
            mechanism=mechanism,
            **kwargs,
        )

    @property
    def lengths(self) -> tuple[int, int, int]:
        """Return the left-wing, gap, and right-wing lengths."""
        return (
            self.left_wing_length,
            self.gap_length,
            self.right_wing_length,
        )

    @property
    def layout(self) -> str:
        """Return the compact wing-gap-wing representation."""
        return "-".join(str(length) for length in self.lengths)


def _positive_length(name: str, value: int) -> int:
    """Return one validated gapmer segment length."""
    if type(value) is not int or value < 1:
        raise ValueError(f"Gapmer {name} must be a positive integer.")
    return value
