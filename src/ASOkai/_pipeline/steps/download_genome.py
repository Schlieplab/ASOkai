#!/usr/bin/env python
"""
Filename: src/ASOkai/_pipeline/steps/download_genome.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Version: 0.1.1
Description: Definition and CLI entrypoint for the download-genome step.
License: LGPL-3.0-or-later
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path
from typing import ClassVar, Literal

from GenomeUtils.Downloaders import EnsemblGenomeDownloader

from ASOkai._cwl.spec import (
    TemplateField,
    OutputPathTemplate,
    OutputParam,
    ScalarParam,
    StepSpec,
)
from ASOkai._pipeline.base import CoreStep


class DownloadGenomeStep(CoreStep):
    name = "download-genome"
    description = "Downloads genome DNA, cDNA, annotation, and a reusable annotation database."
    cli_module = "ASOkai._pipeline.steps.download_genome"
    dependencies: ClassVar[list[str]] = []
    spec = StepSpec(
        doc=(
            "Download genome DNA (primary assembly FASTA), cDNA (FASTA), and "
            "annotation (GTF) from a configured genome source, then build a "
            "reusable annotation database.\nFiles are written "
            "to:\n  {source}/{assembly}/{release}/"
        ),
        requirements={
            "NetworkAccess": {"networkAccess": True},
            "WorkReuse": {"enableReuse": True},
        },
        params=[
            ScalarParam(
                "assembly",
                str,
                config="genome.assembly_id",
                doc="Assembly ID (e.g. GRCh38).",
            ),
            ScalarParam(
                "release",
                int,
                config="genome.ensembl_release",
                doc="Ensembl release number (e.g. 114).",
            ),
            ScalarParam(
                "source",
                Literal["ensembl"],
                config="genome.source",
                doc="Genome data source.",
                default="ensembl",
            ),
            ScalarParam(
                "species",
                str,
                config="genome.species",
                doc="Species name (e.g. Homo_sapiens).",
            ),
        ],
        outputs=[
            OutputParam(
                "dna",
                temp_filename="dna.fa.gz",
                destination=OutputPathTemplate(
                    "{assembly}/genomes/{source}/{release}/"
                    "{species}.{assembly}.dna.primary_assembly.fa.gz",
                    fields={
                        "species": TemplateField(
                            "species",
                            transform="species_case",
                        ),
                    },
                ),
                doc="Primary assembly DNA FASTA ({Species}.{Assembly}.dna.primary_assembly.fa.gz)",
            ),
            OutputParam(
                "cdna",
                temp_filename="cdna.fa.gz",
                destination=OutputPathTemplate(
                    "{assembly}/genomes/{source}/{release}/"
                    "{species}.{assembly}.cdna.all.fa.gz",
                    fields={
                        "species": TemplateField(
                            "species",
                            transform="species_case",
                        ),
                    },
                ),
                doc="cDNA FASTA ({Species}.{Assembly}.cdna.all.fa.gz)",
            ),
            OutputParam(
                "annotation",
                temp_filename="annotation.gtf.gz",
                destination=OutputPathTemplate(
                    "{assembly}/genomes/{source}/{release}/"
                    "{species}.{assembly}.{release}.gtf.gz",
                    fields={
                        "species": TemplateField(
                            "species",
                            transform="species_case",
                        ),
                    },
                ),
                doc="Gene annotation GTF ({Species}.{Assembly}.{release}.gtf.gz)",
            ),
            OutputParam(
                "db",
                temp_filename="annotation.db",
                destination=OutputPathTemplate(
                    "{assembly}/genomes/{source}/{release}/"
                    "{species}.{assembly}.{release}.gtf.db",
                    fields={
                        "species": TemplateField(
                            "species",
                            transform="species_case",
                        ),
                    },
                ),
                doc="Reusable gffutils annotation database.",
            ),
        ],
    )

def _build_parser() -> argparse.ArgumentParser:
    return DownloadGenomeStep().build_parser(
        description="Download genome DNA, cDNA, and GTF.",
    )


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint called by CWL baseCommand: download-genome."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.source != "ensembl":
        parser.error(f"Unsupported genome source: {args.source}")

    outputs = {
        key: getattr(args, f"{key}_output")
        for key in DownloadGenomeStep().spec.output_names()
    }
    output_parents = {path.parent.resolve() for path in outputs.values()}
    if len(output_parents) != 1:
        parser.error("Genome outputs must share one parent directory.")
    output_dir = output_parents.pop()
    output_dir.mkdir(parents=True, exist_ok=True)

    downloader = EnsemblGenomeDownloader(
        assembly_id=args.assembly,
        ensembl_release=args.release,
        species=args.species.lower().replace(" ", "_"),
        genomes_root_dir=output_dir,
    )
    paths = downloader.download(force=True, output_db=True)

    for key, output in outputs.items():
        downloaded = Path(paths[key])
        if downloaded.resolve() != output.resolve():
            shutil.move(str(downloaded), str(output))
        print(f"{key}\t{output}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
