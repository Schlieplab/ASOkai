#!/usr/bin/env python
"""
Filename: src/ASOkai/_pipeline/steps/utils/query_bowtie2.py
Author: Kian Jalilian
Copyright: 2026, Alexander Schliep
Description: Reusable Bowtie 2 alignment of FASTA queries against an index.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

from ASOkai._pipeline.contracts.file_types import (
    Bowtie2IndexDirectory,
    FastaFile,
    SamFile,
)
from ASOkai._pipeline.contracts.files import FileInput, FileOutput
from ASOkai._pipeline.contracts.paths import (
    OutputPathTemplate,
    TemplateField,
)
from ASOkai._pipeline.contracts.step_spec import StepSpec
from ASOkai._pipeline.steps.utils.base import UtilityStep


class QueryBowtie2Step(UtilityStep):
    """Align FASTA queries against a Bowtie 2 index and write SAM."""

    name = "query-bowtie2"
    description = "Aligns FASTA queries against a Bowtie 2 index."
    supports_multiple_threads = True
    index_input = FileInput(
        "index",
        file_type=Bowtie2IndexDirectory(),
        doc="Bowtie 2 index directory to align against.",
    )
    queries_input = FileInput(
        "queries",
        file_type=FastaFile(),
        doc="Plain FASTA query sequences to align.",
    )
    alignments_output = FileOutput(
        "alignments",
        file_type=SamFile(),
        destination=OutputPathTemplate(
            "{assembly}/{source}/{release}/targets/{target}/"
            "analysis/repeated_sites/"
            "{target}_k{k}_{region}_alignments.sam",
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
        doc="SAM alignments of every query against the index.",
    )
    spec = StepSpec(
        requirements={"WorkReuse": {"enableReuse": True}},
        inputs=[index_input, queries_input],
        outputs=[alignments_output],
    )

    def run_from_args(self, args) -> int:
        """Align the queries with Bowtie 2 and write SAM alignments."""
        # TODO: Run ASOkai.Utils.Bowtie2 against
        # Bowtie2IndexDirectory.index_base(args.index) with args.queries as
        # FASTA reads, args.n_threads threads, and args.alignments_output.
        raise NotImplementedError(
            f"Step '{self.name}' is not implemented yet."
        )
