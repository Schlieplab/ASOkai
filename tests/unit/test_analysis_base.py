#!/usr/bin/env python
"""Tests for generic analysis base-class execution."""

import inspect
from typing import cast

import pytest
from GenomeUtils.Genome import Genome

from ASOkai.Analysis import (
    Analysis,
    GenomeWideAnalysis,
    SiteSpecificAnalysis,
    TargetSpecificAnalysis,
)
from ASOkai.Targets import Target


class FakeSite:
    def __init__(self, id, sequence="AT"):
        self.id = id
        self.sequence = sequence


class CountingAnalysis(SiteSpecificAnalysis):
    def analyze(self, site):
        return {"length": len(site.sequence)}


class ContextTargetAnalysis(TargetSpecificAnalysis):
    def analyze(self, site):
        return {"target_id": self.target.id, "site_id": site.id}


class ContextGenomeAnalysis(GenomeWideAnalysis):
    def analyze(self, site):
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


def test_site_specific_run_calls_analyze_for_each_site():
    analysis = CountingAnalysis(sites=[FakeSite("a", "AT"), FakeSite("b", "ATCG")])

    assert isinstance(analysis, Analysis)
    assert analysis.run() == {
        "a": {"length": 2},
        "b": {"length": 4},
    }


def test_site_specific_requires_sites():
    sites_parameter = inspect.signature(CountingAnalysis).parameters["sites"]

    assert sites_parameter.default is inspect.Parameter.empty


def test_site_specific_multiprocessing_matches_serial():
    sites = [FakeSite("a", "AT"), FakeSite("b", "ATCG")]

    assert CountingAnalysis(sites=sites, n_processes=2).run() == CountingAnalysis(
        sites=sites,
        n_processes=1,
    ).run()


def test_analysis_rejects_invalid_process_count():
    with pytest.raises(ValueError, match="n_processes"):
        CountingAnalysis(sites=[FakeSite("a")], n_processes=0)


def test_target_specific_run_exposes_target_context():
    target = cast(Target, FakeTarget("target-1"))
    analysis = ContextTargetAnalysis(target=target, sites=[FakeSite("site-1")])

    assert analysis.run() == {
        "site-1": {"target_id": "target-1", "site_id": "site-1"},
    }


def test_genome_wide_run_exposes_genome_and_target_context():
    genome = cast(Genome, FakeGenome("genome-1"))
    target = cast(Target, FakeTarget("target-1"))
    analysis = ContextGenomeAnalysis(
        genome=genome,
        target=target,
        sites=[FakeSite("site-1")],
    )

    assert analysis.run() == {
        "site-1": {
            "genome_id": "genome-1",
            "target_id": "target-1",
            "site_id": "site-1",
        },
    }
