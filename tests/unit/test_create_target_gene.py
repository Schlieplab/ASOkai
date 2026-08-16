#!/usr/bin/env python
"""Tests for target-gene construction and site extraction."""

from unittest.mock import MagicMock

from Bio.Seq import Seq
from GenomeUtils.Genome import Exon, Strand, Transcript, TranscriptLocus
import pytest

from ASOkai.Sites import TranscriptSite
from ASOkai.Targets import create_target_gene


def _transcript(
    transcript_id: str,
    sequence: str,
    exon_intervals: list[tuple[int, int]],
    *,
    strand: Strand = "+",
) -> Transcript:
    genome = MagicMock()
    transcript = Transcript(
        id=transcript_id,
        chr="12",
        start=min(start for start, _ in exon_intervals),
        end=max(end for _, end in exon_intervals),
        strand=strand,
        sequence=Seq(sequence),
        genome=genome,
    )
    for number, (start, end) in enumerate(exon_intervals, start=1):
        transcript.add_exon(
            Exon(
                id=f"{transcript_id}-E{number}",
                chr="12",
                start=start,
                end=end,
                strand=strand,
                genome=genome,
            )
        )
    return transcript


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


def test_transcriptomic_extraction_without_transcripts_is_empty(
    genome_and_gene,
):
    genome, _ = genome_and_gene

    result = create_target_gene(
        genome,
        target_id="ENSG00000133703",
        site_length=16,
        region="transcriptomic",
    )

    assert result.sites == []


def test_transcriptomic_extraction_includes_overlapping_and_junction_sites(
    genome_and_gene,
):
    genome, gene = genome_and_gene
    gene.transcripts = [
        _transcript(
            "ENST00000001",
            "AACCGGTT",
            [(100, 103), (200, 203)],
        )
    ]

    result = create_target_gene(
        genome,
        target_id="ENSG00000133703",
        site_length=4,
        region="transcriptomic",
    )

    assert all(isinstance(site, TranscriptSite) for site in result.sites)
    assert [str(site.sequence) for site in result.sites] == [
        "AACC",
        "ACCG",
        "CCGG",
        "CGGT",
        "GGTT",
    ]
    assert [site.loci for site in result.sites] == [
        [TranscriptLocus("ENST00000001", start, start + 4)]
        for start in range(5)
    ]


def test_transcriptomic_extraction_merges_sites_shared_by_transcripts(
    genome_and_gene,
):
    genome, gene = genome_and_gene
    gene.transcripts = [
        _transcript(
            "ENST00000002",
            "AACCGGTT",
            [(100, 103), (200, 203)],
        ),
        _transcript(
            "ENST00000001",
            "AACCGGTT",
            [(100, 103), (200, 203)],
        ),
    ]

    result = create_target_gene(
        genome,
        target_id="ENSG00000133703",
        site_length=4,
        region="transcriptomic",
    )

    assert len(result.sites) == 5
    assert result.sites[1].loci == [
        TranscriptLocus("ENST00000001", 1, 5),
        TranscriptLocus("ENST00000002", 1, 5),
    ]


def test_shared_site_can_have_different_coordinates_on_each_transcript(
    genome_and_gene,
):
    genome, gene = genome_and_gene
    gene.transcripts = [
        _transcript("ENST00000002", "TTACGT", [(50, 51), (100, 103)]),
        _transcript("ENST00000001", "ACGT", [(100, 103)]),
    ]

    result = create_target_gene(
        genome,
        target_id="ENSG00000133703",
        site_length=4,
        region="transcriptomic",
    )

    shared_site = result.sites[0]
    assert shared_site.sequence == Seq("ACGT")
    assert shared_site.loci == [
        TranscriptLocus("ENST00000001", 0, 4),
        TranscriptLocus("ENST00000002", 2, 6),
    ]


def test_transcriptomic_extraction_keeps_equal_sequences_at_distinct_loci(
    genome_and_gene,
):
    genome, gene = genome_and_gene
    gene.transcripts = [
        _transcript("ENST00000001", "ACGT", [(100, 103)]),
        _transcript("ENST00000002", "ACGT", [(300, 303)]),
    ]

    result = create_target_gene(
        genome,
        target_id="ENSG00000133703",
        site_length=4,
        region="transcriptomic",
    )

    assert len(result.sites) == 2
    assert [site.loci[0].transcript_id for site in result.sites] == [
        "ENST00000001",
        "ENST00000002",
    ]


def test_transcriptomic_extraction_supports_negative_strand_transcripts(
    genome_and_gene,
):
    genome, gene = genome_and_gene
    gene.transcripts = [
        _transcript(
            "ENST00000001",
            "AACCGGTT",
            [(100, 103), (200, 203)],
            strand="-",
        )
    ]

    result = create_target_gene(
        genome,
        target_id="ENSG00000133703",
        site_length=4,
        region="transcriptomic",
    )

    assert [str(site.sequence) for site in result.sites] == [
        "AACC",
        "ACCG",
        "CCGG",
        "CGGT",
        "GGTT",
    ]
    assert result.sites[1].loci == [
        TranscriptLocus("ENST00000001", 1, 5)
    ]


def test_transcriptomic_extraction_rejects_inconsistent_shared_sequences(
    genome_and_gene,
):
    genome, gene = genome_and_gene
    gene.transcripts = [
        _transcript("ENST00000001", "ACGT", [(100, 103)]),
        _transcript("ENST00000002", "TGCA", [(100, 103)]),
    ]

    with pytest.raises(ValueError, match="disagree on the sequence"):
        create_target_gene(
            genome,
            target_id="ENSG00000133703",
            site_length=4,
            region="transcriptomic",
        )
