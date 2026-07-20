#!/usr/bin/env python
"""Candidate generation from target sites."""

from abc import ABC, abstractmethod

from ..Biochemistry import Chemistry, MechanismOfAction
from ..Sites import Site
from ..Targets import Target
from ._antisense_therapeutic import AntisenseTherapeutic
from ._aso import ASO
from ._binding import Binding


class AntisenseCandidateGenerator(ABC):
    """Base class for modality-specific therapeutic candidate generation."""

    @abstractmethod
    def candidates_for_site(self, site: Site) -> list[AntisenseTherapeutic]:
        """Return candidates designed for one site."""
        raise NotImplementedError

    def generate(
        self,
        target: Target,
    ) -> tuple[list[AntisenseTherapeutic], list[Binding]]:
        therapeutics: list[AntisenseTherapeutic] = []
        bindings: list[Binding] = []
        for site in target.sites:
            for candidate in self.candidates_for_site(site):
                therapeutics.append(candidate)
                bindings.append(Binding(candidate.id, site.id))
        return therapeutics, bindings


class ASOCandidateGenerator(AntisenseCandidateGenerator):
    """Generate one 5'-to-3' reverse-complement ASO for each target site."""

    def __init__(self, chemistry: Chemistry, mechanism: MechanismOfAction):
        self.chemistry = chemistry
        self.mechanism = mechanism

    def candidates_for_site(self, site: Site) -> list[AntisenseTherapeutic]:
        return [
            ASO(
                id=f"{site.id}-ASO-{self.chemistry.id}",
                sequence=site.sequence.reverse_complement(),
                chemistry=self.chemistry,
                mechanism=self.mechanism,
            )
        ]
