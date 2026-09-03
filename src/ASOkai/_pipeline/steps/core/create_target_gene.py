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

from ASOkai.Targets import TargetGene
from ASOkai.Types import TargetRegion
from ASOkai._pipeline.contracts.file_types import JsonFile
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


class CreateTargetGeneStep(CoreStep):
    name = "create-target-gene"
    description = "Creates a target gene object from genome data and extracts target sites."
    target_gene_output = FileOutput(
        "target_gene",
        file_type=JsonFile(TargetGene),
        destination=OutputPathTemplate(
            "{assembly}/genomes/{source}/{release}/{species}/"
            "targets/{target}/{target}_k{k}_{region}.json",
            fields={
                "assembly": TemplateField("genome.assembly_id"),
                "source": TemplateField(
                    "genome.source",
                    default="ensembl",
                ),
                "release": TemplateField("genome.ensembl_release"),
                "species": TemplateField("genome.species"),
                "target": TemplateField.first_of(
                    "target.target_id",
                    "target.target_name",
                ),
                "k": TemplateField("target.k"),
                "region": TemplateField("target.region"),
            },
        ),
        doc="Serialized target gene object.",
    )
    spec = StepSpec(
        requirements={
            "WorkReuse": {"enableReuse": True},
        },
        params=[
            ScalarParam(
                "target_id",
                str | None,
                config="target.target_id",
                doc="Ensembl gene ID (e.g. ENSG00000133703). Use this or target_name.",
            ),
            ScalarParam(
                "target_name",
                str | None,
                config="target.target_name",
                doc="Gene name (e.g. KRAS). Use this or target_id.",
            ),
            ScalarParam("k", int, config="target.k", doc="Target-site length."),
            ScalarParam(
                "region",
                TargetRegion,
                config="target.region",
                doc="Target region type.",
            ),
            ScalarParam("assembly", str, config="genome.assembly_id", doc="Assembly ID (e.g. GRCh38)."),
            ScalarParam("species", str, config="genome.species", doc="Species name (e.g. Homo_sapiens)."),
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
        outputs=[target_gene_output],
    )

    def validate_parameters(self, values: Mapping[str, object]) -> None:
        """Require exactly one target identifier before loading the genome."""
        has_target_id = values.get("target_id") is not None
        has_target_name = values.get("target_name") is not None
        if has_target_id == has_target_name:
            raise ValueError(
                "exactly one of --target-id or --target-name is required"
            )

    def run_from_args(self, args) -> int:
        """Create and serialize the configured target gene."""
        from GenomeUtils.Genome import GenomeBuilder
        from ASOkai.Targets import create_target_gene

        logger.info("create-target-gene: loading DNA FASTA from %s", args.dna)
        builder = GenomeBuilder(
            id=args.assembly,
            species=args.species.replace("_", " "),
            name=args.assembly,
        )
        builder.with_dna_fasta(args.dna)

        logger.info("create-target-gene: loading cDNA FASTA from %s", args.cdna)
        builder.with_cdna_fasta(args.cdna)

        logger.info(
            "create-target-gene: loading GTF annotations from %s using database %s",
            args.annotation,
            args.db,
        )
        builder.with_gtf_file(args.annotation, db_path=args.db)

        logger.info("create-target-gene: indexing genome")
        genome, _ = builder.build()

        logger.info(
            "create-target-gene: extracting %s sites for "
            "target_id=%s target_name=%s k=%s",
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

        logger.info(
            "create-target-gene: writing target gene to %s",
            args.target_gene_output,
        )
        self.target_gene_output.write(
            args.target_gene_output,
            target_gene,
        )

        return 0
