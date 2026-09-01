#!/usr/bin/env python
"""
Filename: tests/unit/test_analysis_base.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Version: 0.1.1
Description: Tests for generic analysis base-class execution.
License: LGPL-3.0-or-later
"""

from threading import Lock
from typing import Any, cast

from Bio.Seq import Seq
import pytest
from GenomeUtils.Genome import Genome

from ASOkai.Analysis import (
    Analysis,
    GenomeWideAnalysis,
    SiteSpecificAnalysis,
    TargetSpecificAnalysis,
)
from ASOkai.Sites import Site
from ASOkai.Targets import TargetGene
from ASOkai.Types import Scalar


class FakeSite(Site):
    def __init__(self, id: str, sequence: str = "AT") -> None:
        super().__init__(id=id, sequence=Seq(sequence))

    def __repr__(self) -> str:
        return f"FakeSite(id={self.id!r})"


class CountingAnalysis(SiteSpecificAnalysis):
    def analyze(self, site: Site) -> dict[str, Scalar]:
        return {"length": len(site.sequence)}


class ContextTargetAnalysis(TargetSpecificAnalysis):
    def analyze(self, site: Site) -> dict[str, Scalar]:
        return {"target_id": self.target.id, "site_id": site.id}


class ContextGenomeAnalysis(GenomeWideAnalysis):
    def analyze(self, site: Site) -> dict[str, Scalar]:
        return {
            "genome_id": self.genome.id,
            "target_id": self.target.id,
            "site_id": site.id,
        }


class FakeTarget:
    def __init__(self, id):
        self.id = id


class FakeGenome:
    def __init__(self, id):
        self.id = id
        self.unpicklable_state = Lock()


def test_site_specific_run_copies_sites_and_analyzes_each_one():
    sites = [FakeSite("a", "AT"), FakeSite("b", "ATCG")]
    analysis = CountingAnalysis(sites=sites)
    sites.clear()

    assert isinstance(analysis, Analysis)
    assert analysis.run() == {
        "a": {"length": 2},
        "b": {"length": 4},
    }
    assert analysis() == {
        "a": {"length": 2},
        "b": {"length": 4},
    }


def test_site_specific_thread_pool_matches_serial():
    sites = [FakeSite("a", "AT"), FakeSite("b", "ATCG")]

    assert CountingAnalysis(sites=sites, n_processes=2).run() == CountingAnalysis(
        sites=sites,
        n_processes=1,
    ).run()


@pytest.mark.parametrize("n_processes", [True, False, 0, -1, 1.5, "2"])
def test_analysis_rejects_invalid_process_count(n_processes):
    with pytest.raises(ValueError, match="n_processes"):
        CountingAnalysis(sites=[FakeSite("a")], n_processes=n_processes)


def test_analysis_rejects_duplicate_site_ids():
    with pytest.raises(ValueError, match="Duplicate analysis site ID: 'a'"):
        CountingAnalysis(sites=[FakeSite("a"), FakeSite("a")])


def test_analysis_rejects_unknown_constructor_arguments():
    with pytest.raises(TypeError, match="unexpected"):
        cast(Any, CountingAnalysis)(
            sites=[FakeSite("a")],
            unexpected=True,
        )


def test_empty_threaded_analysis_returns_no_results():
    assert CountingAnalysis(sites=[], n_processes=2).run() == {}


def test_target_specific_run_exposes_target_context():
    target = cast(TargetGene, FakeTarget("target-1"))
    analysis = ContextTargetAnalysis(target=target, sites=[FakeSite("site-1")])

    assert analysis.run() == {
        "site-1": {"target_id": "target-1", "site_id": "site-1"},
    }


def test_genome_wide_threads_share_unpicklable_genome_and_target_context():
    genome = cast(Genome, FakeGenome("genome-1"))
    target = cast(TargetGene, FakeTarget("target-1"))
    analysis = ContextGenomeAnalysis(
        genome=genome,
        target=target,
        sites=[FakeSite("site-1"), FakeSite("site-2")],
        n_processes=2,
    )

    assert analysis.run() == {
        "site-1": {
            "genome_id": "genome-1",
            "target_id": "target-1",
            "site_id": "site-1",
        },
        "site-2": {
            "genome_id": "genome-1",
            "target_id": "target-1",
            "site_id": "site-2",
        },
    }
