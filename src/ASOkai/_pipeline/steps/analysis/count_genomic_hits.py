#!/usr/bin/env python
"""
Filename: src/ASOkai/_pipeline/steps/analysis/count_genomic_hits.py
Author: Kian Jalilian
Copyright: 2026, Alexander Schliep
Description: Definition of the count-genomic-hits analysis step.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

from ASOkai.Analysis import GenomicHitsAnalysis, SiteGenomicHits
from ASOkai._pipeline.contracts.file_types import CsvFile, JsonFile, SamFile
from ASOkai._pipeline.contracts.files import FileInput, FileOutput
from ASOkai._pipeline.contracts.paths import (
    OutputPathTemplate,
    TemplateField,
)
from ASOkai._pipeline.contracts.step_spec import StepSpec
from ASOkai._pipeline.steps.analysis.table.base import TableAnalysisStep
from ASOkai._pipeline.steps.core.create_target_gene import CreateTargetGeneStep


_GENOMIC_HITS_PATH_FIELDS = {
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
}


class CountGenomicHitsStep(TableAnalysisStep):
    name = "count-genomic-hits"
    description = (
        "Counts the genomic sites at which each target site aligns."
    )
    analysis_cls = GenomicHitsAnalysis
    target_gene_input = FileInput(
        "target_gene",
        source=CreateTargetGeneStep.target_gene_output,
        doc="Serialized target gene object from create-target-gene.",
    )
    alignments_input = FileInput(
        "alignments",
        file_type=SamFile(),
        doc="SAM alignments of the target-site queries, e.g. from query-bowtie2.",
    )
    hit_counts_output = FileOutput(
        "hit_counts",
        file_type=CsvFile(
            index={
                "site_id": str,
            },
            columns={
                "repeated_count": int,
            },
        ),
        destination=OutputPathTemplate(
            "{assembly}/{source}/{release}/targets/{target}/"
            "analysis/repeated_sites/"
            "{target}_k{k}_{region}_genomic_hit_counts.csv",
            fields=_GENOMIC_HITS_PATH_FIELDS,
        ),
        doc="Number of genomic sites at which each target site aligns.",
    )
    genomic_sites_output = FileOutput(
        "genomic_sites",
        file_type=JsonFile(list[SiteGenomicHits]),
        destination=OutputPathTemplate(
            "{assembly}/{source}/{release}/targets/{target}/"
            "analysis/repeated_sites/"
            "{target}_k{k}_{region}_genomic_hits.json",
            fields=_GENOMIC_HITS_PATH_FIELDS,
        ),
        doc="Genomic sites at which each target site aligns.",
    )
    spec = StepSpec(
        requirements={
            "WorkReuse": {"enableReuse": True},
        },
        inputs=[target_gene_input, alignments_input],
        outputs=[hit_counts_output, genomic_sites_output],
        compatible_with={
            "parameters.antisense.modality": ["aso"],
            "parameters.antisense.mechanism": ["rnase-h1"],
            "parameters.antisense.design.type": ["gapmer"],
        },
    )

    def analysis_kwargs(self, args):
        return {"alignments": args.alignments}

    def analysis_units(self, args):
        return args.target_gene.sites

    def additional_output_values(self, analysis, results):
        return {self.genomic_sites_output: analysis.site_hits}
