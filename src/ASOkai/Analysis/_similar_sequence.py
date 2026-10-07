#!/usr/bin/env python
"""
Filename: src/ASOkai/Analysis/_similar_sequence.py
Authors: Arash Ayat, Kian Jalilian
Copyright: 2026, Alexander Schliep
Description: Tree search for sequences an antisense strand binds as well as its target site.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
import multiprocessing
import os
from pathlib import Path
import re
import sys
import time
from typing import Any, ClassVar, Mapping

import RNA
from tqdm import tqdm

from ..Sites import Site
from ..Types import AnalysisUnitType
from ._base import PerUnitAnalysis

_NUCLEOTIDES = "ACGT"
_PROGRESS_DESCRIPTION = "Searching target sites"

#: ViennaRNA's built-in energy parameter sets, by the name used to select one.
ENERGY_PARAMETER_SETS = (
    "RNA_Turner2004",
    "RNA_Turner1999",
    "RNA_Andronescu2007",
    "RNA_Langdon2018",
    "DNA_Mathews2004",
    "DNA_Mathews1999",
)
#: The set ViennaRNA itself uses unless another one is loaded.
DEFAULT_ENERGY_PARAMETERS = "RNA_Turner2004"
_SEQUENCE_ID_PATTERN = re.compile(
    r"(?P<site_id>.+)&n(?P<count>\d+)(?P<mutations>(?:_m\d+[ACGT])*)"
)
_MUTATION_PATTERN = re.compile(r"_m(\d+)([ACGT])")

#: One substitution as a zero-based site position and its new nucleotide.
Mutation = tuple[int, str]

#: One result as its identifier and its sequence, 5' to 3'.
SimilarSequence = tuple[str, str]


def _gapmer_core_positions(gap_length: int, right_wing_length: int) -> range:
    """Return the site positions that pair with a gapmer's central gap.

    A gapmer is the reverse complement of its site, so the two run
    antiparallel: gapmer position ``i`` pairs with site position
    ``site_length - 1 - i``. The gapmer's 5' left wing therefore covers the
    3' end of the site, which places the gap at site positions
    ``right_wing_length`` through ``right_wing_length + gap_length - 1``.

    The step validates that the segment lengths cover the target-site length.
    """
    return range(right_wing_length, right_wing_length + gap_length)


def _similar_sequence_id(site_id: str, mutations: Sequence[Mutation]) -> str:
    """Return the identifier describing one result's substitutions.

    The identifier is ``{site_id}&n{count}`` followed by one ``_m{position}
    {nucleotide}`` group per substitution, with one-based positions. The
    unmutated site is ``{site_id}&n0``. Applying the groups to the site
    sequence reproduces the result, so the identifier alone records the whole
    sequence.
    """
    groups = "".join(
        f"_m{position + 1}{nucleotide}" for position, nucleotide in mutations
    )
    return f"{site_id}&n{len(mutations)}{groups}"


def _parse_similar_sequence_id(
    identifier: str,
) -> tuple[str, tuple[Mutation, ...]]:
    """Return the site ID and zero-based substitutions of a result ID.

    Raises:
        ValueError: If the identifier is malformed or its substitution count
            does not match the groups that follow it.
    """
    match = _SEQUENCE_ID_PATTERN.fullmatch(identifier)
    if match is None:
        raise ValueError(f"Malformed sequence identifier: {identifier!r}.")
    mutations = tuple(
        (int(position) - 1, nucleotide)
        for position, nucleotide in _MUTATION_PATTERN.findall(
            match["mutations"]
        )
    )
    if len(mutations) != int(match["count"]):
        raise ValueError(
            f"Sequence identifier {identifier!r} declares "
            f"{match['count']} substitution(s) but lists {len(mutations)}."
        )
    return match["site_id"], mutations


def _rebuild_sequence(
    site_sequence: str,
    mutations: Sequence[Mutation],
) -> str:
    """Return the sequence produced by substitutions on a target site.

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


def _load_energy_parameters(
    energy_parameters: str,
    energy_parameter_file: str | Path | None,
) -> None:
    """Load the energy parameters every later fold in this process uses.

    ViennaRNA keeps one energy parameter table per process rather than one
    per folding model, so this replaces the table outright. Loading it in the
    parent before any worker is forked lets every worker inherit it.

    Model details bind the loaded table the first time they are folded with,
    so this must run before :func:`_model_details` builds the details used
    for a search.

    Raises:
        ValueError: If the named set is unknown, a file is combined with a
            named set, or the file cannot be read.
    """
    if energy_parameters not in ENERGY_PARAMETER_SETS:
        accepted = ", ".join(ENERGY_PARAMETER_SETS)
        raise ValueError(
            f"Unknown energy parameter set: {energy_parameters!r}. "
            f"Accepted sets are {accepted}."
        )
    if energy_parameter_file is None:
        getattr(RNA, f"params_load_{energy_parameters}")()
        return
    if energy_parameters != DEFAULT_ENERGY_PARAMETERS:
        raise ValueError(
            "Supply either a named energy parameter set or a parameter "
            f"file, not both; received {energy_parameters!r} and "
            f"{str(energy_parameter_file)!r}."
        )
    path = Path(energy_parameter_file).expanduser()
    if not path.is_file():
        raise ValueError(f"Energy parameter file is not a file: {path}.")
    if not RNA.params_load(str(path)):
        raise ValueError(f"ViennaRNA could not read the parameter file {path}.")


def _model_details(model_settings: Mapping[str, Any]) -> Any:
    """Return ViennaRNA model details carrying the supplied settings.

    Raises:
        ValueError: If a setting is not a ViennaRNA model-detail field.
    """
    model_details = RNA.md()
    for name, value in model_settings.items():
        if name.startswith("_") or not hasattr(model_details, name):
            raise ValueError(
                f"Unknown ViennaRNA model setting: {name!r}. Accepted "
                "settings are the fields of RNA.md(), such as 'temperature', "
                "'dangles', 'noGU', 'noLP', or 'salt'."
            )
        setattr(model_details, name, value)
    return model_details


def _mfe(
    sequence: str,
    model_details: Any,
    constraint: str | None = None,
) -> float:
    """Return the minimum free energy of one folded sequence or duplex.

    Raises:
        ValueError: If the constraint cannot be satisfied.
    """
    fold_compound = RNA.fold_compound(sequence, model_details)
    if constraint is not None:
        fold_compound.hc_add_from_db(
            constraint,
            RNA.CONSTRAINT_DB_DEFAULT | RNA.CONSTRAINT_DB_ENFORCE_BP,
        )
    _structure, mfe = fold_compound.mfe()
    if mfe >= 1e4:
        raise ValueError(
            f"The constraint {constraint!r} cannot be satisfied by "
            f"{sequence!r}."
        )
    return mfe


def _core_constraint(site_length: int, core: Iterable[int]) -> str:
    """Return the ``site&strand`` constraint enforcing the core base pairs."""
    site = ["."] * site_length
    strand = ["."] * site_length
    for site_index in core:
        site[site_index] = "("
        strand[site_length - 1 - site_index] = ")"
    return f"{''.join(site)}&{''.join(strand)}"


class SimilarSequenceAnalysis(PerUnitAnalysis):
    """Search each target site for sequences its own antisense strand binds.

    Every site is searched against the reverse complement of that site, which
    is the antisense strand of the gapmer designed for it. The search mutates
    only positions outside the gapmer's central gap, one position per tree
    level, and tries every nucleotide there. The gap's base pairs are enforced
    while folding, so every sequence is scored in the alignment the gapmer
    must form. A sequence is reported when its
    binding energy loss stays within ``max_ddg``, and is explored further
    while the loss stays within ``max_ddg + ddg_tolerance``, because a later
    substitution can restore binding. Every other branch is pruned.

    A reported sequence is only a potential repeated site. It becomes a
    repeated site once a later step finds it in a reference.

    ViennaRNA holds the interpreter lock while folding, so the search runs on
    worker processes.
    """

    analysis_unit_type: ClassVar[AnalysisUnitType] = "site"
    uses_worker_processes = True

    #: Whether to draw a progress bar over the sites being searched.
    show_progress: ClassVar[bool] = True

    def __init__(
        self,
        left_wing_length: int,
        gap_length: int,
        right_wing_length: int,
        *,
        max_ddg: float = 5.0,
        ddg_tolerance: float = 0.5,
        model_settings: Mapping[str, Any] | None = None,
        energy_parameters: str = DEFAULT_ENERGY_PARAMETERS,
        energy_parameter_file: str | Path | None = None,
    ) -> None:
        """Initialize a search for one gapmer layout.

        Args:
            left_wing_length: Nucleotides in the gapmer's left wing.
            gap_length: Nucleotides in the gapmer's central gap.
            right_wing_length: Nucleotides in the gapmer's right wing.
            max_ddg: Largest reported binding-energy loss in kcal/mol.
            ddg_tolerance: Extra loss in kcal/mol that is still explored.
            energy_parameters: Name of a built-in ViennaRNA energy
                parameter set, one of :data:`ENERGY_PARAMETER_SETS`.
            energy_parameter_file: A ViennaRNA parameter file to load instead
                of a named set. The file is read where it lies, so a run
                under CWL needs a path its job can reach.
            model_settings: Extra arguments for ViennaRNA's folding model,
                given as field names of ``RNA.md()`` mapped to values. Common
                fields are ``temperature`` in degrees Celsius, ``dangles``,
                ``noGU``, ``noLP``, and ``salt``. ViennaRNA's own defaults
                apply to every field left out.

        Raises:
            ValueError: If a segment length is not positive, an energy
                threshold is negative, a model setting is unknown, or the
                energy parameters are not selected correctly.
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
        self.model_settings = dict(model_settings or {})
        _model_details(self.model_settings)  # reject unknown settings early
        self.energy_parameters = energy_parameters
        self.energy_parameter_file = energy_parameter_file
        # Reject an unusable selection before any site is searched.
        _load_energy_parameters(energy_parameters, energy_parameter_file)
        # Progress state stays private to whichever process touches it: a
        # forked worker counts only its own sites and never reports back.
        # Progress state, published to forked workers by run().
        self._counter: Any = None
        self._renderer: Any = None
        self._total = 0
        self._started = 0.0
        self._bar: Any = None

    def run(self, units: Iterable[Site], *, n_workers: int = 1) -> list[Any]:
        """Search every site, drawing one progress bar for the whole run.

        The shared counter and the bar are created before any worker is
        forked, so every worker counts into the same total and exactly one
        of them draws the bar.
        """
        # ViennaRNA holds one parameter table per process, so load it here,
        # before super().run() forks the workers that inherit it.
        _load_energy_parameters(
            self.energy_parameters,
            self.energy_parameter_file,
        )
        analysis_units = list(units)
        self._total = len(analysis_units)
        self._bar = None
        # tqdm measures elapsed time against time.time().
        self._started = time.time()
        if self.show_progress and self._total:
            self._counter = multiprocessing.Value("L", 0)
            self._renderer = multiprocessing.Value("L", 0)
        try:
            return super().run(analysis_units, n_workers=n_workers)
        finally:
            self._finish_progress()
            self._counter = self._renderer = None

    def _finish_progress(self) -> None:
        """Leave one complete bar behind once every worker has stopped.

        The drawing worker only refreshes while it is searching, so whichever
        worker finished last leaves the bar short of the total. The shared
        counter survives in this process, so the final bar is drawn here.
        """
        if self._counter is None:
            return
        searched = self._counter.value
        if self._bar is not None:
            self._bar.n = searched
            self._bar.refresh()
            self._bar.close()
            return
        if not searched:
            return
        # A worker drew the bar and cannot close it from here, so overwrite
        # its unfinished line with one complete line in the same format.
        sys.stderr.write(
            "\r"
            + tqdm.format_meter(
                searched,
                self._total,
                time.time() - self._started,
                unit="site",
                prefix=_PROGRESS_DESCRIPTION,
            )
            + "\n"
        )

    def _new_bar(self) -> Any:
        """Return a bar whose elapsed time covers the whole run so far."""
        bar = tqdm(
            total=self._total,
            unit="site",
            desc=_PROGRESS_DESCRIPTION,
            file=sys.stderr,
        )
        bar.start_t = self._started
        return bar

    def _advance_progress(self) -> None:
        """Count one searched site and refresh the bar if this process owns it."""
        if self._counter is None:
            return
        with self._counter.get_lock():
            self._counter.value += 1
            searched = self._counter.value
            if not self._renderer.value:
                self._renderer.value = os.getpid()
        if self._renderer.value != os.getpid():
            return
        if self._bar is None:
            self._bar = self._new_bar()
        self._bar.n = searched
        self._bar.refresh()

    def analyze_unit(self, site: Site) -> list[SimilarSequence]:
        """Search one target site for the sequences its gapmer still binds.

        Returns:
            The unmutated site first, then every distinct sequence ordered by
            binding-energy loss, each as its identifier and its sequence.
        """
        sequence = str(site.sequence).upper()
        strand = str(site.sequence.reverse_complement()).upper()
        length = len(sequence)
        core = set(
            _gapmer_core_positions(self.gap_length, self.right_wing_length)
        )
        constraint = _core_constraint(length, core)
        model_details = _model_details(self.model_settings)
        # Every variant is folded against this one strand, so its own
        # folding energy is computed once instead of once per variant.
        strand_mfe = _mfe(strand, model_details)

        def binding(variant: str) -> float:
            """Return the binding free energy of one variant and the strand."""
            duplex_mfe = _mfe(f"{variant}&{strand}", model_details, constraint)
            return duplex_mfe - (_mfe(variant, model_details) + strand_mfe)

        reference_dg = binding(sequence)
        explore_limit = self.max_ddg + self.ddg_tolerance
        found: dict[str, tuple[tuple[Mutation, ...], float]] = {}
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
                    delta = binding(mutated) - reference_dg
                    if delta > explore_limit:
                        continue
                    mutated_mutations = (*mutations, (position, nucleotide))
                    next_frontier.append((mutated, mutated_mutations))
                    if delta <= self.max_ddg:
                        found[mutated] = (mutated_mutations, delta)
            frontier = next_frontier

        self._advance_progress()
        return [
            (_similar_sequence_id(site.id, ()), sequence),
            *(
                (_similar_sequence_id(site.id, mutations), variant)
                for variant, (mutations, _delta) in sorted(
                    found.items(),
                    key=lambda item: (item[1][1], item[0]),
                )
            ),
        ]
