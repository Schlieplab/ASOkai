#!/usr/bin/env python
"""
Filename: src/ASOkai/_pipeline/steps/core/build_genome_kmer_index.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Definition of the build-genome-kmer-index pipeline step.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Mapping

from ASOkai.Utils import KMC
from ASOkai._pipeline.contracts.file_types import KffFile
from ASOkai._pipeline.contracts.files import FileInput, FileOutput
from ASOkai._pipeline.contracts.parameters import ScalarParam
from ASOkai._pipeline.contracts.paths import OutputPathTemplate, TemplateField
from ASOkai._pipeline.contracts.step_spec import StepSpec
from ASOkai._pipeline.steps.core.base import CoreStep
from ASOkai._pipeline.steps.core.download_genome import DownloadGenomeStep


class BuildGenomeKmerIndexStep(CoreStep):
    """Build one reusable KFF index from the primary genome assembly."""

    name = "build-genome-kmer-index"
    description = "Builds a reusable KFF k-mer index of the genome DNA."
    supports_multiple_processes = True
    dna_input = FileInput(
        "dna",
        source=DownloadGenomeStep.dna_output,
        doc="Primary assembly DNA FASTA from download-genome.",
    )
    kmer_index_output = FileOutput(
        "kmer_index",
        file_type=KffFile(),
        destination=OutputPathTemplate(
            "{assembly}/{source}/{release}/genome/indexes/kmc/"
            "{assembly}.k{k}.kff",
            fields={
                "assembly": TemplateField("genome.assembly_id"),
                "source": TemplateField("genome.source", default="ensembl"),
                "release": TemplateField("genome.ensembl_release"),
                "k": TemplateField("target.k"),
            },
        ),
        doc="Canonical genome k-mer counts in KFF format.",
    )
    spec = StepSpec(
        requirements={"WorkReuse": {"enableReuse": True}},
        params=[
            ScalarParam(
                "k",
                int,
                config="target.k",
                doc="K-mer length used to build the genome index.",
            ),
        ],
        inputs=[dna_input],
        outputs=[kmer_index_output],
    )

    def validate_parameters(self, values: Mapping[str, object]) -> None:
        """Require a k-mer size supported by KMC."""
        k = values.get("k")
        if type(k) is not int or not 1 <= k <= 256:
            raise ValueError("k must be between 1 and 256")

    def run_from_args(self, args) -> int:
        """Count canonical genome k-mers and write one KFF index."""
        output = Path(args.kmer_index_output)
        with TemporaryDirectory(
            prefix="asokai-kmc-",
            dir=Path.cwd(),
        ) as working_directory:
            KMC().run(
                args.dna,
                output,
                working_directory,
                k=args.k,
                m=4,
                f="fm",
                t=args.n_processes,
                ci=1,
                o="kff",
                hp=True,
                debug=False,
            )

        return 0
