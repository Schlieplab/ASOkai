#!/usr/bin/env python
"""
Filename: src/ASOkai/_pipeline/steps/analysis/intrinsic_features.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Definition of the intrinsic-features analysis step.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

from ASOkai.Analysis import IntrinsicFeaturesAnalysis
from ASOkai._pipeline.contracts.file_types import CsvFile
from ASOkai._pipeline.contracts.files import FileInput, FileOutput
from ASOkai._pipeline.contracts.paths import (
    OutputPathTemplate,
    TemplateField,
)
from ASOkai._pipeline.contracts.step_spec import StepSpec
from ASOkai._pipeline.steps.analysis.base import AnalysisStep
from ASOkai._pipeline.steps.core.create_target_gene import CreateTargetGeneStep


class IntrinsicFeaturesStep(AnalysisStep):
    name = "intrinsic-features"
    description = (
        "Computes nucleotide composition and CpG features for each " "target site."
    )
    analysis_cls = IntrinsicFeaturesAnalysis
    target_gene_input = FileInput(
        "target_gene",
        source=CreateTargetGeneStep.target_gene_output,
        doc="Serialized target gene object from create-target-gene.",
    )
    intrinsic_features_output = FileOutput(
        "intrinsic_features",
        file_type=CsvFile(
            index={
                "site_id": str,
            },
            columns={
                "GC_content": float,
                "AT_content": float,
                "T_count": int,
                "CpG_count": int,
                "T_content": float,
                "CpG_content": float,
            },
        ),
        destination=OutputPathTemplate(
            "{assembly}/{source}/{release}/targets/{target}/"
            "analysis/intrinsic/"
            "{target}_k{k}_{region}_intrinsic.csv",
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
        doc="Intrinsic features per target site.",
    )
    spec = StepSpec(
        requirements={
            "WorkReuse": {"enableReuse": True},
        },
        inputs=[target_gene_input],
        outputs=[intrinsic_features_output],
    )

    def analysis_units(self, args):
        return args.target_gene.sites
