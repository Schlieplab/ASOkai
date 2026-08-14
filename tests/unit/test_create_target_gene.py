#!/usr/bin/env python
"""Tests for target-gene construction and site extraction."""

from unittest.mock import MagicMock

import pytest

from ASOkai.Targets import create_target_gene


@pytest.fixture
def genome_and_gene(sample_sequence):
    gene = MagicMock()
    gene.id = "ENSG00000133703"
    gene.name = "KRAS"
    gene.chr = "12"
    gene.start = 100
    gene.end = 500
    gene.strand = "+"
    gene.sequence = sample_sequence
    gene.transcripts = []
    gene.get_chromosome.return_value = None

    genome = MagicMock()
    genome.gene_by_id.return_value = gene
    genome.gene_by_name.return_value = gene
    genome.get_sequence_by_locus.return_value = sample_sequence
    return genome, gene


@pytest.mark.parametrize(
    ("target_id", "target_name"),
    [(None, None), ("ENSG00000133703", "KRAS")],
)
def test_requires_exactly_one_gene_identifier(
    genome_and_gene,
    target_id,
    target_name,
):
    genome, _ = genome_and_gene

    with pytest.raises(
        ValueError,
        match="exactly one of target_id or target_name",
    ):
        create_target_gene(
            genome,
            target_id=target_id,
            target_name=target_name,
            site_length=16,
        )


def test_creates_gene_and_sites_by_gene_id(genome_and_gene):
    genome, gene = genome_and_gene

    result = create_target_gene(
        genome,
        target_id="ENSG00000133703",
        site_length=16,
        region="pre-mrna",
    )

    genome.gene_by_id.assert_called_once_with("ENSG00000133703")
    genome.gene_by_name.assert_not_called()
    assert result.id == gene.id
    assert result.name == gene.name
    assert result.sites[0].id == "ASOkai-ENSG00000133703-Premrna-S00001"


def test_creates_gene_and_sites_by_gene_name(genome_and_gene):
    genome, gene = genome_and_gene

    result = create_target_gene(
        genome,
        target_name="KRAS",
        site_length=16,
        region="pre-mrna",
    )

    genome.gene_by_name.assert_called_once_with("KRAS")
    genome.gene_by_id.assert_not_called()
    assert result.id == gene.id
    assert result.sites[0].id == "ASOkai-KRAS-Premrna-S00001"


def test_transcriptomic_extraction_is_explicitly_pending(genome_and_gene):
    genome, _ = genome_and_gene

    with pytest.raises(
        NotImplementedError,
        match="Transcriptomic target-site extraction",
    ):
        create_target_gene(
            genome,
            target_id="ENSG00000133703",
            site_length=16,
            region="transcriptomic",
        )
