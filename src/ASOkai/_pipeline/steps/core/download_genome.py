#!/usr/bin/env python
"""
Filename: src/ASOkai/_pipeline/steps/core/download_genome.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Version: 0.1.1
Description: Definition of the download-genome pipeline step.
License: LGPL-3.0-or-later
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Literal

from GenomeUtils.Downloaders import EnsemblGenomeDownloader

from ASOkai._pipeline.contracts.file_types import FileType
from ASOkai._pipeline.contracts.files import FileOutput
from ASOkai._pipeline.contracts.parameters import ScalarParam
from ASOkai._pipeline.contracts.paths import (
    OutputPathTemplate,
    TemplateField,
)
from ASOkai._pipeline.contracts.step_spec import StepSpec
from ASOkai._pipeline.steps.core.base import CoreStep


_GENOME_PATH_FIELDS = {
    "assembly": TemplateField("genome.assembly_id"),
    "source": TemplateField("genome.source"),
    "release": TemplateField("genome.ensembl_release"),
    "species": TemplateField("genome.species"),
}


class DownloadGenomeStep(CoreStep):
    name = "download-genome"
    description = "Downloads genome DNA, cDNA, annotation, and a reusable annotation database."
    dna_output = FileOutput(
        "dna",
        file_type=FileType(
            media_type="application/gzip",
            format_name="gzip-compressed DNA FASTA",
        ),
        destination=OutputPathTemplate(
            "{assembly}/genomes/{source}/{release}/"
            "{species}.{assembly}.dna.primary_assembly.fa.gz",
            fields=_GENOME_PATH_FIELDS,
        ),
        doc="Primary assembly DNA FASTA.",
    )
    cdna_output = FileOutput(
        "cdna",
        file_type=FileType(
            media_type="application/gzip",
            format_name="gzip-compressed cDNA FASTA",
        ),
        destination=OutputPathTemplate(
            "{assembly}/genomes/{source}/{release}/"
            "{species}.{assembly}.cdna.all.fa.gz",
            fields=_GENOME_PATH_FIELDS,
        ),
        doc="All-transcript cDNA FASTA.",
    )
    annotation_output = FileOutput(
        "annotation",
        file_type=FileType(
            media_type="application/gzip",
            format_name="gzip-compressed GTF",
        ),
        destination=OutputPathTemplate(
            "{assembly}/genomes/{source}/{release}/"
            "{species}.{assembly}.{release}.gtf.gz",
            fields=_GENOME_PATH_FIELDS,
        ),
        doc="Gene annotation GTF.",
    )
    db_output = FileOutput(
        "db",
        file_type=FileType(
            media_type="application/vnd.sqlite3",
            format_name="SQLite gffutils database",
        ),
        destination=OutputPathTemplate(
            "{assembly}/genomes/{source}/{release}/"
            "{species}.{assembly}.{release}.gtf.db",
            fields=_GENOME_PATH_FIELDS,
        ),
        doc="Reusable annotation database built by gffutils.",
    )
    spec = StepSpec(
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
            dna_output,
            cdna_output,
            annotation_output,
            db_output,
        ],
    )

    def run_from_args(self, args) -> int:
        """Download the configured genome files."""
        outputs = {
            output.name: getattr(args, output.argument_name)
            for output in self.spec.outputs
        }
        output_dir = next(iter(outputs.values())).parent.resolve()

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
