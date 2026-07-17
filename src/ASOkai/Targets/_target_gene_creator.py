#!/usr/bin/env python
"""
Filename: src/ASOkai/Targets/_target_gene_creator.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Version: 0.1.1
Description: This file defines the TargetGeneCreator for creating TargetGene objects.
License: LGPL-3.0-or-later
"""
from ._target_creator import TargetCreator
from ._target_gene import TargetGene
from GenomeUtils.Genome import Genome, Gene, Exon, Locus
from typing import Dict, Set, List, Iterator, Literal, Optional, cast
from Bio.Seq import Seq
from ..Sites import Site
from ..Sites import GenomicSite
from ..Sites import TranscriptSite


# Module-level helper functions for site extraction

def _validated_strand(value: str) -> Literal["+", "-"]:
    if value not in ("+", "-"):
        raise ValueError(f"Invalid strand: {value!r}")
    return cast(Literal["+", "-"], value)

def _extract_exonic_only_sites(gene: Gene, genome: Genome, k: int, id_generator: Iterator[str]) -> Dict[str, GenomicSite]:
    """
    Extracts genomic sites from a Gene object's exons.
    
    Args:
        gene: The Gene object to extract sites from.
        genome: The Genome object to get sequences from.
        k: The length of the target sites.
        id_generator: Iterator that generates unique IDs for sites.
        
    Returns:
        A dictionary of sites.
    """
    sorted_exons: List[Exon] = []
    
    # Collect unique exons from all transcripts
    all_exons: Set[Exon] = set()
    for transcript in gene.transcripts:
        for exon in transcript.exons:
            all_exons.add(exon)
    
    sorted_exons = sorted(list(all_exons), key=lambda x: x.start)
    
    sites = {}
    
    # Extract sites from each exon
    for exon_idx, exon in enumerate(sorted_exons):
        for i in range(len(exon) - k + 1):
            id = next(id_generator)
            site_start = exon.start + i
            site_end = exon.start + i + k - 1
            strand = _validated_strand(exon.strand)
            site = GenomicSite(
                id=id,
                chr=exon.chr,
                start=site_start,
                end=site_end,
                strand=strand,
                sequence=genome.get_sequence_by_locus(Locus(exon.chr, site_start, site_end, strand)),
            )
            sites[site.id] = site
    
    return sites


def _extract_pre_mrna_sites(gene: Gene, genome: Genome, k: int, id_generator: Iterator[str]) -> Dict[str, GenomicSite]:
    """
    Extracts genomic sites from a Gene object's entire sequence, including introns and exons.
    
    Args:
        gene: The Gene object to extract sites from.
        genome: The Genome object to get sequences from.
        k: The length of the target sites.
        id_generator: Iterator that generates unique IDs for sites.
        
    Returns:
        A dictionary of sites.
    """
    sites = {}
    for i in range(len(gene.sequence) - k + 1):
        id = next(id_generator)
        site_start = gene.start + i
        site_end = gene.start + i + k - 1
        strand = _validated_strand(gene.strand)
        site = GenomicSite(
            id=id,
            chr=gene.chr,
            start=site_start,
            end=site_end,
            strand=strand,
            sequence=genome.get_sequence_by_locus(Locus(gene.chr, site_start, site_end, strand)),
        )
        sites[site.id] = site
    return sites


def _extract_transcript_sites(gene: Gene, id_generator: Iterator[str]) -> Dict[str, TranscriptSite]:
    """
    Extracts transcript sites from a Gene object.
    
    Args:
        gene: The Gene object to extract sites from.
        id_generator: Iterator that generates unique IDs for sites.
        
    Returns:
        A dictionary of sites.
    """
    raise NotImplementedError


class TargetGeneCreator(TargetCreator):
    """
    Creator for TargetGene objects using factory methods.
    This class is not meant to be instantiated.
    """

    @classmethod
    def from_genome(
        cls,
        genome: Genome,
        target_id: Optional[str] = None,
        target_name: Optional[str] = None,
        *,
        k: int,
        region: str = "exonic_only",
    ) -> TargetGene:
        """
        Creates a `TargetGene` object from a gene ID or name within a `Genome` object.

        Args:
            genome: The Genome object to create the TargetGene from.
            target_id: The ID of the gene to create the TargetGene from. Provide this or target_name.
            target_name: The gene symbol/name (e.g. KRAS). Provide this or target_id.
            k: Length of the target sites.
            region: The region to create the TargetGene from. Can be one of:
            - "exonic_only": Creates the TargetGene from the exons of the gene.
            - "pre-mrna": Creates the TargetGene from the entire gene sequence, including introns and exons.
            - "transcriptomic": Creates the TargetGene from the spliced transcripts of the gene.

        Returns:
            A `TargetGene` object.
        """
        if (target_id is None) == (target_name is None):
            raise ValueError("Provide exactly one of target_id or target_name")

        if target_id is not None:
            gene_to_target = genome.gene_by_id(target_id)
        else:
            assert target_name is not None
            gene_to_target = genome.gene_by_name(target_name)
            
        gene_sequence = gene_to_target.sequence
        gene_name_clean = gene_to_target.name.replace(" ", "_")
        
        if region == "exonic_only":
            id_generator = cls.site_id_generator(extra_prefix_parts=[gene_name_clean, "Exon"])
            sites = _extract_exonic_only_sites(gene_to_target, genome, k, id_generator)
        elif region == "pre-mrna":
            id_generator = cls.site_id_generator(extra_prefix_parts=[gene_name_clean, "Premrna"])
            sites = _extract_pre_mrna_sites(gene_to_target, genome, k, id_generator)
        elif region == "transcriptomic":
            id_generator = cls.site_id_generator(extra_prefix_parts=[gene_name_clean, "Transcript"])
            sites = _extract_transcript_sites(gene_to_target, id_generator)
        else:
            raise ValueError(f"Invalid region: {region}")
        
        target_gene = TargetGene(
            id=gene_to_target.id,
            name=gene_to_target.name,
            chr=gene_to_target.chr,
            start=gene_to_target.start,
            end=gene_to_target.end,
            strand=_validated_strand(gene_to_target.strand),
            sequence=gene_sequence,
            sites=sites,
            genome=genome,
            chromosome=gene_to_target.get_chromosome(),
        )
    
        return target_gene
    
    @classmethod
    def from_file(cls, file_path: str) -> TargetGene:
        """
        Load a TargetGene object from a file.
        """
        raise NotImplementedError
    
