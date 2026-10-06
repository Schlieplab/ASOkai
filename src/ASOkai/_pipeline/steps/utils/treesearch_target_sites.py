#!/usr/bin/env python
"""
Filename: src/ASOkai/_pipeline/steps/utils/treesearch_target_sites.py
Author: Kian Jalilian
Copyright: 2026, Alexander Schliep
Description: Tree search that turns target sites into Bowtie 2 query sequences.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

from ASOkai._pipeline.contracts.file_types import FastaFile
from ASOkai._pipeline.contracts.files import FileInput, FileOutput
from ASOkai._pipeline.contracts.paths import (
    OutputPathTemplate,
    TemplateField,
)
from ASOkai._pipeline.contracts.step_spec import StepSpec
from ASOkai._pipeline.steps.core.create_target_gene import CreateTargetGeneStep
from ASOkai._pipeline.steps.utils.base import UtilityStep


class TreesearchTargetSitesStep(UtilityStep):
    """Write the query sequences found by a tree search over target sites."""

    name = "treesearch-target-sites"
    description = (
        "Runs a tree search over target sites and writes Bowtie 2 queries."
    )
    target_gene_input = FileInput(
        "target_gene",
        source=CreateTargetGeneStep.target_gene_output,
        doc="Serialized target gene from create-target-gene by default.",
    )
    queries_output = FileOutput(
        "queries",
        file_type=FastaFile(),
        destination=OutputPathTemplate(
            "{assembly}/{source}/{release}/targets/{target}/"
            "analysis/repeated_sites/"
            "{target}_k{k}_{region}_queries.fa",
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
        doc="Query sequences for Bowtie 2, one FASTA record per query.",
    )
    spec = StepSpec(
        requirements={"WorkReuse": {"enableReuse": True}},
        inputs=[target_gene_input],
        outputs=[queries_output],
        compatible_with={
            "parameters.antisense.modality": ["aso"],
            "parameters.antisense.mechanism": ["rnase-h1"],
            "parameters.antisense.design.type": ["gapmer"],
        },
    )

    def run_from_args(self, args) -> int:
        """Search the target sites and write the resulting query FASTA."""
        # TODO: Run the tree search over args.target_gene.sites and write the
        # queries to args.queries_output.
        raise NotImplementedError(
            f"Step '{self.name}' is not implemented yet."
        )
