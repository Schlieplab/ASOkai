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

    layout: str

    def __init__(
        self,
        id: str,
        sequence: Seq,
        mechanism: MechanismOfAction,
        layout: str = "3-10-3",
        **kwargs,
    ):
        """Initialize a gapmer.

        Args:
            id: Unique therapeutic identifier.
            sequence: Antisense-strand sequence in the 5' to 3' direction.
            mechanism: Mechanism through which the gapmer acts.
            layout: Positive left-wing, gap, and right-wing lengths formatted
                as ``<left wing>-<gap>-<right wing>``.
            kwargs: Additional scalar values retained during serialization.
        """
        try:
            lengths = tuple(int(part) for part in layout.split("-"))
        except (AttributeError, ValueError) as error:
            raise ValueError(
                "Gapmer layout must have the form "
                "'<left wing>-<gap>-<right wing>'."
            ) from error
        if len(lengths) != 3 or any(length < 1 for length in lengths):
            raise ValueError(
                "Gapmer layout must contain three positive lengths, "
                "for example '3-10-3'."
            )
        self.layout = "-".join(str(length) for length in lengths)
        super().__init__(
            id=id,
            sequence=sequence,
            mechanism=mechanism,
            **kwargs,
        )

    @property
    def lengths(self) -> tuple[int, int, int]:
        """Return the left-wing, gap, and right-wing lengths."""
        left_wing, gap, right_wing = (
            int(part) for part in self.layout.split("-")
        )
        return left_wing, gap, right_wing

    @property
    def left_wing_length(self) -> int:
        """Return the length of the left wing."""
        return self.lengths[0]

    @property
    def gap_length(self) -> int:
        """Return the length of the central gap."""
        return self.lengths[1]

    @property
    def right_wing_length(self) -> int:
        """Return the length of the right wing."""
        return self.lengths[2]
