#!/usr/bin/env python
"""
Filename: src/ASOkai/Antisense/_candidate_generator.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Candidate generation from target sites.
License: LGPL-3.0-or-later
"""

from abc import ABC, abstractmethod
from collections.abc import Iterable

from ..Biochemistry import MechanismOfAction
from ..Sites import Site
from ._antisense_therapeutic import AntisenseTherapeutic
from ._aso import ASO
from ._binding import Binding
from ._gapmer import Gapmer
from ._oligonucleotide import Oligonucleotide
from ._sirna import siRNA


class AntisenseCandidateGenerator(ABC):
    """Base class for modality-specific therapeutic candidate generation."""

    @abstractmethod
    def candidates_for_site(self, site: Site) -> list[AntisenseTherapeutic]:
        """Return candidates designed for one site."""
        raise NotImplementedError

    def generate(
        self,
        sites: Iterable[Site],
    ) -> tuple[list[AntisenseTherapeutic], list[Binding]]:
        """Generate candidates and their site bindings in input order."""
        therapeutics: list[AntisenseTherapeutic] = []
        bindings: list[Binding] = []
        for site in sites:
            for candidate in self.candidates_for_site(site):
                therapeutics.append(candidate)
                bindings.append(Binding(candidate.id, site.id))
        return therapeutics, bindings


class ASOCandidateGenerator(AntisenseCandidateGenerator):
    """Generate one 5'-to-3' reverse-complement ASO for each target site."""

    def __init__(self, mechanism: MechanismOfAction):
        """Initialize an unmodified-ASO generator for one mechanism."""
        self.mechanism = mechanism

    def candidates_for_site(self, site: Site) -> list[AntisenseTherapeutic]:
        """Return one reverse-complement ASO for ``site``."""
        return [
            ASO(
                id=f"{site.id}-ASO",
                sequence=site.sequence.reverse_complement(),
                mechanism=self.mechanism,
            )
        ]


class GapmerCandidateGenerator(ASOCandidateGenerator):
    """Generate one wing-gap-wing ASO for each target site."""

    def __init__(
        self,
        mechanism: MechanismOfAction,
        left_wing_length: int,
        gap_length: int,
        right_wing_length: int,
    ):
        """Initialize a gapmer generator with one wing-gap-wing layout."""
        super().__init__(mechanism=mechanism)
        self.left_wing_length = left_wing_length
        self.gap_length = gap_length
        self.right_wing_length = right_wing_length

    def candidates_for_site(self, site: Site) -> list[AntisenseTherapeutic]:
        """Return one reverse-complement gapmer for ``site``."""
        return [
            Gapmer(
                id=f"{site.id}-Gapmer",
                sequence=site.sequence.reverse_complement(),
                mechanism=self.mechanism,
                left_wing_length=self.left_wing_length,
                gap_length=self.gap_length,
                right_wing_length=self.right_wing_length,
            )
        ]


class SiRNACandidateGenerator(AntisenseCandidateGenerator):
    """Generate one siRNA duplex for each target site."""

    def __init__(self, mechanism: MechanismOfAction):
        """Initialize an siRNA generator for one mechanism."""
        self.mechanism = mechanism

    def candidates_for_site(self, site: Site) -> list[AntisenseTherapeutic]:
        """Return one complementary guide/passenger duplex for ``site``."""
        return [
            siRNA(
                id=f"{site.id}-siRNA",
                antisense_strand=Oligonucleotide(
                    sequence=site.sequence.reverse_complement(),
                ),
                sense_strand=Oligonucleotide(sequence=site.sequence),
                mechanism=self.mechanism,
            )
        ]
