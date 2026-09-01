#!/usr/bin/env python
"""Tests for the TargetGene aggregate."""

from Bio.Seq import Seq
import pytest

from ASOkai.Sites import GenomicSite
from ASOkai.Targets import TargetGene


@pytest.fixture
def sites(sample_sequence):
    return {
        f"site-{index}": GenomicSite(
            id=f"site-{index}",
            chr="12",
            start=100 + index * 20,
            end=115 + index * 20,
            strand="+",
            sequence=sample_sequence,
        )
        for index in range(3)
    }


@pytest.fixture
def target_gene(sites):
    return TargetGene(
        id="ENSG00000001",
        name="TEST_GENE",
        chr="12",
        start=100,
        end=155,
        strand="+",
        sequence=Seq("A" * 56),
        sites=sites,
    )


def test_target_gene_contains_gene_data_and_copies_sites(target_gene, sites):
    sites.clear()

    assert target_gene.id == "ENSG00000001"
    assert target_gene.name == "TEST_GENE"
    assert target_gene.sequence == Seq("A" * 56)
    assert [site.id for site in target_gene.sites] == [
        "site-0",
        "site-1",
        "site-2",
    ]


def test_target_gene_requires_sequence_to_match_locus_length():
    with pytest.raises(
        ValueError,
        match="same length as the target-gene sequence",
    ):
        TargetGene(
            id="ENSG00000001",
            name="TEST_GENE",
            chr="12",
            start=1,
            end=4,
            strand="+",
            sequence=Seq("A"),
            sites={},
        )


def test_target_gene_requires_site_keys_to_match_site_ids(sample_sequence):
    site = GenomicSite(
        id="site-id",
        chr="12",
        start=1,
        end=16,
        strand="+",
        sequence=sample_sequence,
    )

    with pytest.raises(ValueError, match="must match site ID 'site-id'"):
        TargetGene(
            id="ENSG00000001",
            name="TEST_GENE",
            chr="12",
            start=1,
            end=16,
            strand="+",
            sequence=sample_sequence,
            sites={"wrong-key": site},
        )


def test_target_gene_finds_site_by_id(target_gene):
    assert target_gene.site_by_id("site-1").id == "site-1"

    with pytest.raises(ValueError, match="not found"):
        target_gene.site_by_id("missing")


def test_target_gene_adds_and_removes_sites(target_gene):
    site = GenomicSite(
        id="new-site",
        chr="12",
        start=200,
        end=203,
        strand="+",
        sequence=Seq("ACGT"),
    )

    target_gene.add_site(site)
    assert target_gene.site_by_id("new-site") is site

    with pytest.raises(ValueError, match="already exists"):
        target_gene.add_site(site)

    target_gene.remove_site("new-site")
    with pytest.raises(ValueError, match="not found"):
        target_gene.remove_site("new-site")
