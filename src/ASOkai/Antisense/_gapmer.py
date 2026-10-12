#!/usr/bin/env python
"""
Filename: src/ASOkai/Antisense/_gapmer.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: This file defines the Gapmer class.
License: LGPL-3.0-or-later
"""

from Bio.Seq import Seq

from ..Biochemistry import Chemistry, MechanismOfAction
from ._aso import ASO


class Gapmer(ASO):
    """An ASO with a wing-gap-wing design."""

    left_wing_length: int
    gap_length: int
    right_wing_length: int

    def __init__(
        self,
        sequence: Seq,
        mechanism: MechanismOfAction,
        left_wing_length: int,
        gap_length: int,
        right_wing_length: int,
        *,
        chemistry: Chemistry | None = None,
        id: str | None = None,
        **kwargs,
    ):
        """Initialize a gapmer.

        Args:
            id: Optional stored ID, checked against the design-derived ID.
            sequence: Antisense-strand sequence in the 5' to 3' direction.
            mechanism: Mechanism through which the gapmer acts.
            left_wing_length: Number of nucleotides in the left wing.
            gap_length: Number of nucleotides in the central gap.
            right_wing_length: Number of nucleotides in the right wing.
            chemistry: Optional chemistry of this strand.
            kwargs: Additional serializable metadata attributes.

        Raises:
            ValueError: If a segment length is not a positive integer or the
                segment lengths do not sum to the sequence length.
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
        design_length = sum(self.lengths)
        if design_length != len(sequence):
            raise ValueError(
                "Gapmer segment lengths must equal the sequence length "
                f"({len(sequence)}); received {design_length}."
            )
        super().__init__(
            id=id,
            sequence=sequence,
            mechanism=mechanism,
            chemistry=chemistry,
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

    def _design_id(self) -> str:
        """Include the wing-gap-wing layout in the ASO design ID."""
        chemistry = (
            self._identity_suffix("c", self.chemistry.id)
            if self.chemistry else ""
        )
        return (
            f"gapmer:l{self.left_wing_length}g{self.gap_length}"
            f"r{self.right_wing_length}-m{self.mechanism.id}-"
            f"{self._sequence_token(self.sequence)}{chemistry}"
        )


def _positive_length(name: str, value: int) -> int:
    """Return one validated gapmer segment length."""
    if type(value) is not int or value < 1:
        raise ValueError(f"Gapmer {name} must be a positive integer.")
    return value
