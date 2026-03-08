#!/usr/bin/env python
"""
Filename: src/ASOkai/targets/target_gene_creator.py
Author: Arash Ayat
Copyright: 2025, Alexander Schliep
Version: 0.1.0
Description: This file defines the TargetGeneCreator for creating TargetGene objects.
License: LGPL-3.0-or-later
"""
from .target_creator import TargetCreator
from .target_gene import TargetGene
from GenomeUtils.Genome import Genome, Gene, Exon, Locus
from typing import Literal, Dict, Set, List, Iterator
from Bio.Seq import Seq
from ..sites import Site
from ..sites import GenomicSite
from ..sites import TranscriptSite


# Module-level helper functions for site extraction

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
    print("sorted_exons", sorted_exons)
    
    sites = {}
    
    # Extract sites from each exon
    for exon_idx, exon in enumerate(sorted_exons):
        for i in range(len(exon) - k + 1):
            id = next(id_generator)
            site_start = exon.start + i
            site_end = exon.start + i + k - 1
            site = GenomicSite(
                id=id,
                chr=exon.chr,
                start=site_start,
                end=site_end,
                strand=exon.strand,
                sequence=genome.get_sequence_by_locus(Locus(exon.chr, site_start, site_end, exon.strand)),
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
        site = GenomicSite(
            id=id,
            chr=gene.chr,
            start=site_start,
            end=site_end,
            strand=gene.strand,
            sequence=genome.get_sequence_by_locus(Locus(gene.chr, site_start, site_end, gene.strand)),
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
    pass


class TargetGeneCreator(TargetCreator):
    """
    Creator for TargetGene objects using factory methods.
    This class is not meant to be instantiated.
    """

    @classmethod
    def from_genome(cls, genome: Genome, target_id: str, k: int, region: str = "exonic_only") -> TargetGene:
        """
        Creates a `TargetGene` object from a gene ID within a `Genome` object.
        Args:
            genome: The Genome object to create the TargetGene from.
            target_id: The ID of the gene to create the TargetGene from.
            k: length of the target sites.
            region: The region to create the TargetGene from. Can be one of:
            - "exonic_only": Creates the TargetGene from the exons of the gene.
            - "pre-mrna": Creates the TargetGene from the entire gene sequence, including introns and exons.
            - "transcriptomic": Creates the TargetGene from the spliced transcripts of the gene.
        
        Returns:
            A `TargetGene` object.
        """
        gene_to_target = genome.gene_by_id(target_id)
        gene_sequence = gene_to_target.sequence
        
        # Create ID generator with appropriate prefix
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
            strand=gene_to_target.strand,
            sequence=gene_sequence,
            sites=sites,
            genome=genome,
            chromosome=gene_to_target.get_chromosome(),
        )
    
        return target_gene
    
    @classmethod
    def from_file(cls, file_path: str):
        """
        Load a TargetGene object from a file.
        """
        pass
    