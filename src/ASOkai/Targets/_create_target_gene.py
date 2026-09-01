#!/usr/bin/env python
"""
Filename: src/ASOkai/Targets/_create_target_gene.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Version: 0.1.1
Description: Target-gene construction and target-site extraction.
License: LGPL-3.0-or-later
"""

from collections.abc import Iterator
from typing import cast

from Bio.Seq import Seq
from GenomeUtils.Genome import Gene, Genome, Locus, TranscriptLocus

from ..Types import Strand, TargetRegion
from ..Sites import GenomicSite, TranscriptSite
from ._target_gene import TargetGene


def _validated_strand(value: str) -> Strand:
    if value not in ("+", "-"):
        raise ValueError(f"Invalid strand: {value!r}")
    return cast(Strand, value)


def _site_ids(target: str, region: str) -> Iterator[str]:
    number = 1
    while True:
        yield f"ASOkai-{target}-{region}-S{number:05d}"
        number += 1


def _extract_exonic_sites(
    gene: Gene,
    genome: Genome,
    site_length: int,
    site_ids: Iterator[str],
) -> dict[str, GenomicSite]:
    """Extract every target site wholly contained in an exon."""
    site_loci = {
        Locus(
            exon.chr,
            exon.start + offset,
            exon.start + offset + site_length - 1,
            _validated_strand(exon.strand),
        )
        for transcript in gene.transcripts
        for exon in transcript.exons
        for offset in range(len(exon) - site_length + 1)
    }
    sites: dict[str, GenomicSite] = {}
    for locus in sorted(site_loci):
        site_id = next(site_ids)
        sites[site_id] = GenomicSite(
            id=site_id,
            chr=locus.chr,
            start=locus.start,
            end=locus.end,
            strand=locus.strand,
            sequence=genome.get_sequence_by_locus(locus),
        )
    return sites


def _extract_pre_mrna_sites(
    gene: Gene,
    genome: Genome,
    site_length: int,
    site_ids: Iterator[str],
) -> dict[str, GenomicSite]:
    """Extract every target site from the gene's genomic span."""
    sites: dict[str, GenomicSite] = {}
    strand = _validated_strand(gene.strand)
    for offset in range(len(gene.sequence) - site_length + 1):
        site_id = next(site_ids)
        start = gene.start + offset
        end = start + site_length - 1
        site = GenomicSite(
            id=site_id,
            chr=gene.chr,
            start=start,
            end=end,
            strand=strand,
            sequence=genome.get_sequence_by_locus(
                Locus(gene.chr, start, end, strand)
            ),
        )
        sites[site_id] = site
    return sites


def _extract_transcript_sites(
    gene: Gene,
    site_length: int,
    site_ids: Iterator[str],
) -> dict[str, TranscriptSite]:
    """Extract target sites from each spliced transcript."""
    occurrences_by_genomic_loci: dict[
        tuple[Locus, ...],
        list[tuple[Seq, TranscriptLocus]],
    ] = {}

    for transcript in sorted(gene.transcripts, key=lambda item: item.id):
        for start in range(len(transcript.sequence) - site_length + 1):
            transcript_locus = TranscriptLocus(
                transcript.id,
                start,
                start + site_length,
            )
            genomic_loci = tuple(
                transcript.to_genomic_loci(transcript_locus)
            )
            sequence = transcript.sequence[
                transcript_locus.start:transcript_locus.end
            ]
            occurrences_by_genomic_loci.setdefault(
                genomic_loci,
                [],
            ).append((sequence, transcript_locus))

    sites: dict[str, TranscriptSite] = {}
    for genomic_loci, occurrences in occurrences_by_genomic_loci.items():
        sequence = occurrences[0][0]
        if any(other_sequence != sequence for other_sequence, _ in occurrences):
            raise ValueError(
                "Transcripts disagree on the sequence at shared genomic "
                f"loci {genomic_loci!r}."
            )
        site_id = next(site_ids)
        sites[site_id] = TranscriptSite(
            id=site_id,
            loci=[locus for _, locus in occurrences],
            sequence=sequence,
        )
    return sites


def create_target_gene(
    genome: Genome,
    target_id: str | None = None,
    target_name: str | None = None,
    *,
    site_length: int,
    region: TargetRegion = "exonic",
) -> TargetGene:
    """Create a target gene and extract all sites in one target region.

    Args:
        genome: Indexed genome containing the requested gene.
        target_id: Gene identifier. Mutually exclusive with ``target_name``.
        target_name: Gene name. Mutually exclusive with ``target_id``.
        site_length: Positive target-site length in nucleotides.
        region: ``exonic`` for sites contained within individual exons,
            ``pre-mrna`` for the complete genomic gene span, or
            ``transcriptomic`` for spliced transcript sequences.

    Returns:
        A target-gene snapshot containing sites in deterministic order.

    Raises:
        ValueError: If the identifier selection, site length, region, or
            extracted domain data is invalid.
    """
    if (target_id is None) == (target_name is None):
        raise ValueError("Provide exactly one of target_id or target_name")
    if site_length < 1:
        raise ValueError("site_length must be at least 1")
    if region not in ("exonic", "pre-mrna", "transcriptomic"):
        raise ValueError(f"Invalid region: {region}")

    if target_id is not None:
        gene = genome.gene_by_id(target_id)
        target_label = target_id
    else:
        assert target_name is not None
        gene = genome.gene_by_name(target_name)
        target_label = target_name

    if region == "exonic":
        sites = _extract_exonic_sites(
            gene,
            genome,
            site_length,
            _site_ids(target_label, "Exon"),
        )
    elif region == "pre-mrna":
        sites = _extract_pre_mrna_sites(
            gene,
            genome,
            site_length,
            _site_ids(target_label, "Premrna"),
        )
    else:
        sites = _extract_transcript_sites(
            gene,
            site_length,
            _site_ids(target_label, "Transcript"),
        )

    return TargetGene(
        id=gene.id,
        name=gene.name,
        chr=gene.chr,
        start=gene.start,
        end=gene.end,
        strand=_validated_strand(gene.strand),
        sequence=gene.sequence,
        sites=sites,
        genome=genome,
        chromosome=gene.get_chromosome(),
    )
