#!/usr/bin/env python
"""
Filename: src/ASOkai/_pipeline/steps/core/create_target_gene.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Definition of the create-target-gene pipeline step.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

import logging
from typing import Mapping

from Bio import SeqIO
from Bio.SeqRecord import SeqRecord
from GenomeUtils.Genome import Genome

from ASOkai.Targets import TargetGene
from ASOkai.Types import TargetRegion
from ASOkai._pipeline.contracts.file_types import FastaFile, JsonFile
from ASOkai._pipeline.contracts.files import FileInput, FileOutput
from ASOkai._pipeline.contracts.parameters import ScalarParam
from ASOkai._pipeline.contracts.paths import (
    OutputPathTemplate,
    TemplateField,
)
from ASOkai._pipeline.contracts.step_spec import StepSpec
from ASOkai._pipeline.steps.core.base import CoreStep
from ASOkai._pipeline.steps.core.download_genome import DownloadGenomeStep

logger = logging.getLogger(__name__)


def _fasta_records(
    genome: Genome, target_gene: TargetGene, region: TargetRegion
) -> list[SeqRecord]:
    """Return the selected gene's full region sequences in a stable order."""
    if region == "pre-mrna":
        return [
            SeqRecord(
                target_gene.sequence,
                id=target_gene.id,
                description=target_gene.name,
            )
        ]

    gene = genome.gene_by_id(target_gene.id)
    if region == "exonic":
        exons_by_locus = {exon.locus: exon for exon in gene.exons}
        records = [
            SeqRecord(
                exons_by_locus[locus].sequence,
                id=(
                    f"{target_gene.id}:exon:{locus.chr}:"
                    f"{locus.start}-{locus.end}:{locus.strand}"
                ),
                description=target_gene.name,
            )
            for locus in sorted(exons_by_locus)
        ]
    elif region == "transcriptomic":
        records = [
            SeqRecord(
                transcript.sequence,
                id=transcript.id,
                description=target_gene.name,
            )
            for transcript in sorted(gene.transcripts, key=lambda item: item.id)
        ]
    else:
        raise ValueError(f"Invalid target region: {region!r}.")

    if not records:
        raise ValueError(f"Target gene {target_gene.id!r} has no {region} sequences.")
    return records


class CreateTargetGeneStep(CoreStep):
    name = "create-target-gene"
    description = (
        "Creates a target gene, extracts target sites, and writes a region FASTA."
    )
    target_gene_output = FileOutput(
        "target_gene",
        file_type=JsonFile(TargetGene),
        destination=OutputPathTemplate(
            "{assembly}/{source}/{release}/targets/{target}/"
            "{target}_k{k}_{region}.json",
            fields={
                "assembly": TemplateField("parameters.genome.assembly"),
                "source": TemplateField(
                    "parameters.genome.source",
                    default="ensembl",
                ),
                "release": TemplateField("parameters.genome.release"),
                "target": TemplateField.first_of(
                    "parameters.target.target_id",
                    "parameters.target.target_name",
                ),
                "k": TemplateField("parameters.target.k"),
                "region": TemplateField("parameters.target.region"),
            },
        ),
        doc="Serialized target gene object.",
    )
    fasta_output = FileOutput(
        "fasta",
        file_type=FastaFile(),
        destination=OutputPathTemplate(
            "{assembly}/{source}/{release}/targets/{target}/"
            "{target}_k{k}_{region}.fa",
            fields=target_gene_output.destination.fields,
        ),
        doc=(
            "Full pre-mRNA sequence, distinct exon sequences, or spliced "
            "transcript sequences according to the selected target region."
        ),
    )
    spec = StepSpec(
        requirements={
            "WorkReuse": {"enableReuse": True},
        },
        params=[
            ScalarParam(
                "target_id",
                str | None,
                config="parameters.target.target_id",
                doc="Ensembl gene ID (e.g. ENSG00000133703). Use this or target_name.",
            ),
            ScalarParam(
                "target_name",
                str | None,
                config="parameters.target.target_name",
                doc="Gene name (e.g. KRAS). Use this or target_id.",
            ),
            ScalarParam(
                "k", int, config="parameters.target.k", doc="Target-site length."
            ),
            ScalarParam(
                "region",
                TargetRegion,
                config="parameters.target.region",
                doc="Target region type.",
            ),
            ScalarParam(
                "assembly",
                str,
                config="parameters.genome.assembly",
                doc="Assembly ID (e.g. GRCh38).",
            ),
            ScalarParam(
                "species",
                str,
                config="parameters.genome.species",
                doc="Species name (e.g. Homo_sapiens).",
            ),
        ],
        inputs=[
            FileInput(
                "dna",
                source=DownloadGenomeStep.dna_output,
                doc="Primary assembly FASTA from download-genome.",
            ),
            FileInput(
                "cdna",
                source=DownloadGenomeStep.cdna_output,
                doc="cDNA FASTA from download-genome.",
            ),
            FileInput(
                "annotation",
                source=DownloadGenomeStep.annotation_output,
                doc="GTF annotation file from download-genome.",
            ),
            FileInput(
                "db",
                source=DownloadGenomeStep.db_output,
                doc="Reusable annotation database from download-genome.",
            ),
        ],
        outputs=[target_gene_output, fasta_output],
    )

    def validate_parameters(self, values: Mapping[str, object]) -> None:
        """Require exactly one target identifier before loading the genome."""
        has_target_id = values.get("target_id") is not None
        has_target_name = values.get("target_name") is not None
        if has_target_id == has_target_name:
            raise ValueError("exactly one of --target-id or --target-name is required")

    def run_from_args(self, args) -> int:
        """Create and serialize the configured target gene."""
        from GenomeUtils.Genome import GenomeBuilder
        from ASOkai.Targets import create_target_gene

        logger.info("Loading DNA FASTA")
        logger.debug("DNA FASTA input: %s", args.dna)
        builder = GenomeBuilder(
            id=args.assembly,
            species=args.species.replace("_", " "),
            name=args.assembly,
        )
        builder.with_dna_fasta(args.dna)

        logger.info("Loading cDNA FASTA")
        logger.debug("cDNA FASTA input: %s", args.cdna)
        builder.with_cdna_fasta(args.cdna)

        logger.info("Loading GTF annotations")
        logger.debug(
            "GTF input: %s; annotation database: %s",
            args.annotation,
            args.db,
        )
        builder.with_gtf_file(args.annotation, db_path=args.db)

        logger.info("Indexing genome")
        genome, _ = builder.build()

        logger.info(
            "Extracting %s sites for " "target_id=%s target_name=%s k=%s",
            args.region,
            args.target_id,
            args.target_name,
            args.k,
        )
        target_gene = create_target_gene(
            genome,
            target_id=args.target_id,
            target_name=args.target_name,
            site_length=args.k,
            region=args.region,
        )
        fasta_records = _fasta_records(genome, target_gene, args.region)

        logger.info(
            "Writing target gene to %s",
            args.target_gene_output,
        )
        self.target_gene_output.write(
            args.target_gene_output,
            target_gene,
        )
        logger.info("Writing target FASTA to %s", args.fasta_output)
        with args.fasta_output.open("w", encoding="utf-8") as stream:
            SeqIO.write(fasta_records, stream, "fasta")

        return 0
