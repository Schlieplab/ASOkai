#!/usr/bin/env python
"""
Filename: src/ASOkai/_pipeline/steps/analysis/intrinsic_features.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Version: 0.1.1
Description: Definition of the intrinsic-features analysis step.
License: LGPL-3.0-or-later
"""
from __future__ import annotations

from ASOkai.Types import TargetRegion
from ASOkai.Analysis import IntrinsicFeaturesAnalysis
from ASOkai._pipeline.file_types import JsonFile
from ASOkai._pipeline.files import FileInput, FileOutput
from ASOkai._pipeline.parameters import ScalarParam
from ASOkai._pipeline.paths import OutputPathTemplate, TemplateField
from ASOkai._pipeline.step_spec import StepSpec
from ASOkai._pipeline.steps.analysis.base import AnalysisStep
from ASOkai._pipeline.steps.core.create_target_gene import CreateTargetGeneStep


class IntrinsicFeaturesStep(AnalysisStep):
    name = "intrinsic-features"
    description = "Computes intrinsic features (GC content, T-runs, AT-runs) for each ASO target site."
    analysis_cls = IntrinsicFeaturesAnalysis
    target_gene_input = FileInput(
        "target_gene",
        source=CreateTargetGeneStep.target_gene_output,
        override="target.target_gene_path",
        doc="Serialized target gene object from create-target-gene.",
    )
    intrinsic_features_output = FileOutput(
        "intrinsic_features",
        file_type=JsonFile(),
        destination=OutputPathTemplate(
            "{assembly}/targets/{target}/analysis/intrinsic/"
            "{target}_k{k}_{region}_intrinsic.json",
            fields={
                "target": TemplateField.first_of(
                    "target_id",
                    "target_name",
                ),
            },
        ),
        doc="Intrinsic features per ASO target site.",
    )
    spec = StepSpec(
        requirements={
            "WorkReuse": {"enableReuse": True},
        },
        params=[
            ScalarParam("assembly", str, config="genome.assembly_id", doc="Assembly ID (e.g. GRCh38)."),
            ScalarParam(
                "target_id",
                str | None,
                config="target.target_id",
                doc="Ensembl gene ID. Takes priority over target_name.",
            ),
            ScalarParam(
                "target_name",
                str | None,
                config="target.target_name",
                doc="Gene name. Used if target_id is not provided.",
            ),
            ScalarParam("k", int, config="target.k", doc="ASO length."),
            ScalarParam(
                "region",
                TargetRegion,
                config="target.region",
                doc="Target region type.",
            ),
        ],
        inputs=[target_gene_input],
        outputs=[intrinsic_features_output],
    )

    def analysis_kwargs(self, args) -> dict:
        return {
            "sites": args.target_gene.sites,
        }
