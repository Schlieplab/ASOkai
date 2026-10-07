#!/usr/bin/env python
"""
Filename: src/ASOkai/Analysis/_treesearch_target_sites.py
Author: Kian Jalilian
Copyright: 2026, Alexander Schliep
Description: Tree search for target-site variants that an antisense strand still binds.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
import logging
import os
import re
import time
from typing import Any, ClassVar, Mapping

from ..Sites import Site
from ..Types import AnalysisUnitType
from ..Utils import binding_dg
from ._base import PerUnitAnalysis

logger = logging.getLogger(__name__)

_NUCLEOTIDES = "ACGT"
_CANDIDATE_ID_PATTERN = re.compile(
    r"(?P<site_id>.+)_n(?P<count>\d+)(?P<mutations>(?:_m\d+[ACGT])*)"
)
_MUTATION_PATTERN = re.compile(r"_m(\d+)([ACGT])")

#: One substitution as a zero-based site position and its new nucleotide.
Mutation = tuple[int, str]


def gapmer_core_positions(
    site_length: int,
    left_wing_length: int,
    gap_length: int,
    right_wing_length: int,
) -> range:
    """Return the site positions that pair with a gapmer's central gap.

    A gapmer is the reverse complement of its site, so the two run
    antiparallel: gapmer position ``i`` pairs with site position
    ``site_length - 1 - i``. The gapmer's 5' left wing therefore covers the
    3' end of the site, which places the gap at site positions
    ``right_wing_length`` through ``right_wing_length + gap_length - 1``.

    Raises:
        ValueError: If the segment lengths do not sum to the site length.
    """
    if left_wing_length + gap_length + right_wing_length != site_length:
        raise ValueError(
            "Gapmer segment lengths must equal the site length "
            f"({site_length}); received "
            f"{left_wing_length + gap_length + right_wing_length}."
        )
    return range(right_wing_length, right_wing_length + gap_length)


def candidate_id(site_id: str, mutations: Sequence[Mutation]) -> str:
    """Return the identifier describing one candidate's substitutions.

    The identifier is ``{site_id}_n{count}`` followed by one ``_m{position}
    {nucleotide}`` group per substitution, with one-based positions. The
    unmutated site is ``{site_id}_n0``. Applying the groups to the site
    sequence reproduces the candidate, so the identifier alone records the
    whole variant.
    """
    groups = "".join(
        f"_m{position + 1}{nucleotide}" for position, nucleotide in mutations
    )
    return f"{site_id}_n{len(mutations)}{groups}"


def parse_candidate_id(identifier: str) -> tuple[str, tuple[Mutation, ...]]:
    """Return the site ID and zero-based substitutions of a candidate ID.

    Raises:
        ValueError: If the identifier is malformed or its substitution count
            does not match the groups that follow it.
    """
    match = _CANDIDATE_ID_PATTERN.fullmatch(identifier)
    if match is None:
        raise ValueError(f"Malformed candidate identifier: {identifier!r}.")
    mutations = tuple(
        (int(position) - 1, nucleotide)
        for position, nucleotide in _MUTATION_PATTERN.findall(
            match["mutations"]
        )
    )
    if len(mutations) != int(match["count"]):
        raise ValueError(
            f"Candidate identifier {identifier!r} declares "
            f"{match['count']} substitution(s) but lists {len(mutations)}."
        )
    return match["site_id"], mutations


def rebuild_sequence(
    site_sequence: str,
    mutations: Sequence[Mutation],
) -> str:
    """Return the candidate sequence produced by substitutions on a site.

    Raises:
        ValueError: If a substitution lies outside the site sequence.
    """
    bases = list(site_sequence)
    for position, nucleotide in mutations:
        if not 0 <= position < len(bases):
            raise ValueError(
                f"Substitution at position {position} lies outside a site of "
                f"length {len(bases)}."
            )
        bases[position] = nucleotide
    return "".join(bases)


@dataclass(frozen=True)
class CandidateRepeatedSite:
    """A site variant whose antisense strand binding stays within a threshold.

    Candidates are only potential repeated sites. They become repeated sites
    once a later step finds them in a reference.
    """

    #: ID of the target site this candidate was searched from.
    site_id: str
    #: Candidate sequence, 5' to 3'.
    sequence: str
    #: Substitutions relative to the target site, ordered by position.
    mutations: tuple[Mutation, ...]
    #: Binding free energy of the candidate and the strand in kcal/mol.
    dg_binding: float
    #: ``dg_binding`` minus the target site's own binding energy.
    ddg_binding: float

    @property
    def id(self) -> str:
        """Return the identifier recording this candidate's substitutions."""
        return candidate_id(self.site_id, self.mutations)

    @property
    def is_reference(self) -> bool:
        """Return whether this candidate is the unmutated target site."""
        return not self.mutations


def _core_constraint(site_length: int, core: Iterable[int]) -> str:
    """Return the ``site&strand`` constraint enforcing the core base pairs."""
    site = ["."] * site_length
    strand = ["."] * site_length
    for site_index in core:
        site[site_index] = "("
        strand[site_length - 1 - site_index] = ")"
    return f"{''.join(site)}&{''.join(strand)}"


class TreesearchTargetSitesAnalysis(PerUnitAnalysis):
    """Search each target site for variants its own antisense strand binds.

    Every site is searched against the reverse complement of that site, which
    is the antisense strand of the gapmer designed for it. The search mutates
    only positions outside the gapmer's central gap, one position per tree
    level, and tries every nucleotide there. A variant is reported when its
    binding energy loss stays within ``max_ddg``, and is explored further
    while the loss stays within ``max_ddg + ddg_tolerance``, because a later
    substitution can restore binding. Every other branch is pruned.

    ViennaRNA holds the interpreter lock while folding, so the search runs on
    worker processes.
    """

    analysis_unit_type: ClassVar[AnalysisUnitType] = "site"
    uses_worker_processes = True

    #: Sites one process searches between progress lines; 0 logs nothing.
    progress_interval: ClassVar[int] = 1000

    def __init__(
        self,
        left_wing_length: int,
        gap_length: int,
        right_wing_length: int,
        *,
        max_ddg: float = 5.0,
        ddg_tolerance: float = 0.5,
        constrain_core: bool = True,
        model_settings: Mapping[str, Any] | None = None,
    ) -> None:
        """Initialize a candidate search for one gapmer layout.

        Args:
            left_wing_length: Nucleotides in the gapmer's left wing.
            gap_length: Nucleotides in the gapmer's central gap.
            right_wing_length: Nucleotides in the gapmer's right wing.
            max_ddg: Largest reported binding-energy loss in kcal/mol.
            ddg_tolerance: Extra loss in kcal/mol that is still explored.
            constrain_core: Whether to enforce the gap's base pairs when
                folding each duplex.
            model_settings: Extra arguments for ViennaRNA's folding model,
                such as ``temperature`` or ``noGU``. See
                :func:`ASOkai.Utils.binding_dg`.

        Raises:
            ValueError: If a segment length is not positive or an energy
                threshold is negative.
        """
        lengths = (left_wing_length, gap_length, right_wing_length)
        if any(type(length) is not int or length < 1 for length in lengths):
            raise ValueError("Gapmer segment lengths must be positive integers.")
        if max_ddg < 0 or ddg_tolerance < 0:
            raise ValueError("max_ddg and ddg_tolerance must be non-negative.")
        self.left_wing_length = left_wing_length
        self.gap_length = gap_length
        self.right_wing_length = right_wing_length
        self.max_ddg = max_ddg
        self.ddg_tolerance = ddg_tolerance
        self.constrain_core = constrain_core
        self.model_settings = dict(model_settings or {})
        # Progress state stays private to whichever process touches it: a
        # forked worker counts only its own sites and never reports back.
        self._searched = 0
        self._started = 0.0

    def analyze_unit(self, site: Site) -> list[CandidateRepeatedSite]:
        """Search one target site for the variants its gapmer still binds.

        Returns:
            The unmutated site first, then every distinct candidate ordered
            by binding-energy loss and sequence.
        """
        sequence = str(site.sequence).upper()
        strand = str(site.sequence.reverse_complement()).upper()
        length = len(sequence)
        core = set(
            gapmer_core_positions(
                length,
                self.left_wing_length,
                self.gap_length,
                self.right_wing_length,
            )
        )
        constraint = (
            _core_constraint(length, core) if self.constrain_core else None
        )

        def binding(variant: str) -> float:
            return binding_dg(
                variant,
                strand,
                constraint=constraint,
                model_settings=self.model_settings,
            )

        reference_dg = binding(sequence)
        explore_limit = self.max_ddg + self.ddg_tolerance
        found: dict[str, tuple[tuple[Mutation, ...], float, float]] = {}
        frontier: list[tuple[str, tuple[Mutation, ...]]] = [(sequence, ())]
        for position in range(length):
            if position in core:
                continue
            next_frontier: list[tuple[str, tuple[Mutation, ...]]] = []
            for variant, mutations in frontier:
                # Leaving this position unchanged reuses a scored variant.
                next_frontier.append((variant, mutations))
                for nucleotide in _NUCLEOTIDES:
                    if nucleotide == variant[position]:
                        continue
                    mutated = (
                        f"{variant[:position]}{nucleotide}"
                        f"{variant[position + 1:]}"
                    )
                    dg = binding(mutated)
                    delta = dg - reference_dg
                    if delta > explore_limit:
                        continue
                    mutated_mutations = (*mutations, (position, nucleotide))
                    next_frontier.append((mutated, mutated_mutations))
                    if delta <= self.max_ddg:
                        found[mutated] = (mutated_mutations, dg, delta)
            frontier = next_frontier

        self._report_progress()
        return [
            CandidateRepeatedSite(site.id, sequence, (), reference_dg, 0.0),
            *(
                CandidateRepeatedSite(site.id, variant, mutations, dg, delta)
                for variant, (mutations, dg, delta) in sorted(
                    found.items(),
                    key=lambda item: (item[1][2], item[0]),
                )
            ),
        ]

    def _report_progress(self) -> None:
        """Log how many sites this process has searched, now and then."""
        if not self.progress_interval:
            return
        if not self._searched:
            self._started = time.monotonic()
        self._searched += 1
        if self._searched % self.progress_interval:
            return
        elapsed = time.monotonic() - self._started
        logger.info(
            "Searched %d sites in worker %d (%.1f sites/s)",
            self._searched,
            os.getpid(),
            self._searched / elapsed if elapsed else 0.0,
        )
