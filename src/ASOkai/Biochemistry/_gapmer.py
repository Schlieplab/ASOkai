#!/usr/bin/env python
"""Gapmer chemistry."""

from ._chemistry import Chemistry


class GapmerChemistry(Chemistry):
    """A wing-gap-wing oligonucleotide chemistry."""

    def __init__(self, layout: str = "3-10-3", **kwargs):
        try:
            lengths = tuple(int(part) for part in layout.split("-"))
        except (AttributeError, ValueError) as error:
            raise ValueError(
                "Gapmer layout must have the form '<left wing>-<gap>-<right wing>'."
            ) from error
        if len(lengths) != 3 or any(length < 1 for length in lengths):
            raise ValueError(
                "Gapmer layout must contain three positive lengths, for example '3-10-3'."
            )

        self.layout = "-".join(str(length) for length in lengths)
        super().__init__(**kwargs)

    @property
    def lengths(self) -> tuple[int, int, int]:
        left, gap, right = (int(part) for part in self.layout.split("-"))
        return left, gap, right

    @property
    def left_wing_length(self) -> int:
        return self.lengths[0]

    @property
    def gap_length(self) -> int:
        return self.lengths[1]

    @property
    def right_wing_length(self) -> int:
        return self.lengths[2]

    @property
    def id(self) -> str:
        return f"gapmer-{self.layout}"
