#!/usr/bin/env python
"""
Filename: src/ASOkai/Targets/_target_gene.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Version: 0.1.1
Description: Target gene and its extracted target sites.
License: LGPL-3.0-or-later
"""
from typing import Mapping, cast

from Bio.Seq import Seq
from GenomeUtils.Genome import Chromosome, Gene, Genome, Locus

from ..Sites import Site
from ..Utils import Serializable
from ..Types import Strand


class TargetGene(Serializable, Gene):
    """A gene together with the target sites extracted from it."""

    id: str
    name: str
    locus: Locus
    _sequence: Seq
    _sites: dict[str, Site]
    _non_serializable_attrs = {"_genome", "_parent", "_children"}

    def __init__(
        self,
        id: str,
        name: str,
        chr: str,
        start: int,
        end: int,
        strand: Strand,
        sequence: Seq,
        sites: Mapping[str, Site],
        genome: Genome | None = None,
        chromosome: Chromosome | None = None,
        **kwargs,
    ):
        """Initialize a target gene.

        Args:
            id: Gene ID.
            name: Gene name.
            chr: Chromosome containing the gene.
            start: 1-based inclusive genomic start coordinate.
            end: 1-based inclusive genomic end coordinate.
            strand: Gene strand.
            sequence: The gene sequence in the 5' to 3' direction.
            sites: Target sites keyed by their unique site IDs.
            genome: Optional parent genome reference.
            chromosome: Optional parent chromosome reference.
            **kwargs: Additional scalar values retained during serialization.
        """
        self._sequence = sequence
        self._sites = dict(sites)
        Serializable.__init__(self, **kwargs)
        Gene.__init__(
            self,
            id,
            name,
            chr,
            start,
            end,
            strand,
            genome=cast(Genome, genome),
            chromosome=cast(Chromosome, chromosome),
        )

    @property
    def sequence(self) -> Seq:
        """Return the target-gene sequence in the 5' to 3' direction."""
        return self._sequence

    @property
    def sites(self) -> list[Site]:
        """Return the target sites in their creation order."""
        return list(self._sites.values())

    def site_by_id(self, site_id: str) -> Site:
        """Return the target site identified by ``site_id``."""
        try:
            return self._sites[site_id]
        except KeyError as error:
            raise ValueError(
                f"Target site with ID '{site_id}' not found."
            ) from error

    def add_site(self, site: Site) -> None:
        """Add a target site whose ID is not already present."""
        if site.id in self._sites:
            raise ValueError(
                f"Target site with ID '{site.id}' already exists."
            )
        self._sites[site.id] = site

    def remove_site(self, site_id: str) -> None:
        """Remove the target site identified by ``site_id``."""
        try:
            del self._sites[site_id]
        except KeyError as error:
            raise ValueError(
                f"Target site with ID '{site_id}' not found."
            ) from error
