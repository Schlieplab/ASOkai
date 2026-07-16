#!/usr/bin/env python
"""
Filename: src/ASOkai/_pipeline/steps/create_target_gene.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Version: 0.1.1
Description: Definition and CLI entrypoint for the create-target-gene step.
License: LGPL-3.0-or-later
"""
from __future__ import annotations

import argparse
import logging
import sys
from typing import ClassVar, Literal

from ASOkai._cwl.spec import (
    TemplateField,
    OutputPathTemplate,
    InputParam,
    OutputParam,
    ScalarParam,
    StepSpec,
)
from ASOkai._pipeline.base import CoreStep


logger = logging.getLogger(__name__)


class CreateTargetGeneStep(CoreStep):
    name = "create-target-gene"
    description = "Creates a target gene object from genome data and extracts ASO target sites."
    cli_module = "ASOkai._pipeline.steps.create_target_gene"
    dependencies: ClassVar[list[str]] = ["download-genome"]
    spec = StepSpec(
        requirements={
            "WorkReuse": {"enableReuse": True},
        },
        params=[
            ScalarParam(
                "target_id",
                str | None,
                config="target.target_id",
                doc="Ensembl gene ID (e.g. ENSG00000133703). Takes priority over target_name.",
            ),
            ScalarParam(
                "target_name",
                str | None,
                config="target.target_name",
                doc="Gene name (e.g. KRAS). Used if target_id is not provided.",
            ),
            ScalarParam("k", int, config="target.k", doc="ASO length."),
            ScalarParam(
                "region",
                Literal["exonic_only", "pre-mrna", "transcriptomic"],
                config="target.region",
                doc="Target region type.",
            ),
            ScalarParam("assembly", str, config="genome.assembly_id", doc="Assembly ID (e.g. GRCh38)."),
            ScalarParam("release", int, config="genome.ensembl_release", doc="Ensembl release number (e.g. 114)."),
            ScalarParam("species", str, config="genome.species", doc="Species name (e.g. Homo_sapiens)."),
        ],
        inputs=[
            InputParam("dna", override="genome.dna_path", doc="Primary assembly FASTA from download-genome."),
            InputParam("cdna", override="genome.cdna_path", doc="cDNA FASTA from download-genome."),
            InputParam("annotation", override="genome.annotation_path", doc="GTF annotation file from download-genome."),
            InputParam("db", override="genome.db_path", doc="Reusable annotation database from download-genome."),
        ],
        outputs=[
            OutputParam(
                "target_gene",
                temp_filename="target_gene.json",
                destination=OutputPathTemplate(
                    "{assembly}/targets/{target}/{target}_k{k}_{region}.json",
                    fields={
                        "target": TemplateField.first_of(
                            "target_id",
                            "target_name",
                        ),
                    },
                ),
                doc="Serialized target gene object.",
            ),
        ],
    )

def _build_parser() -> argparse.ArgumentParser:
    return CreateTargetGeneStep().build_parser(
        description="Create a target gene object and extract ASO target sites.",
    )


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint called by CWL baseCommand: create-target-gene."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    args.target_gene_output.parent.mkdir(parents=True, exist_ok=True)

    if not args.target_id and not args.target_name:
        parser.error("Either --target-id or --target-name is required.")

    from GenomeUtils.Genome import GenomeBuilder
    from ASOkai.Targets import TargetGeneCreator

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
        "create-target-gene: extracting %s sites for target_id=%s target_name=%s k=%s",
        args.region,
        args.target_id,
        args.target_name,
        args.k,
    )
    target_gene = TargetGeneCreator.from_genome(
        genome,
        target_id=args.target_id,
        target_name=args.target_name,
        k=args.k,
        region=args.region,
    )

    logger.info("create-target-gene: writing target gene to %s", args.target_gene_output)
    target_gene.to_file(str(args.target_gene_output))

    return 0


if __name__ == "__main__":
    sys.exit(main())
