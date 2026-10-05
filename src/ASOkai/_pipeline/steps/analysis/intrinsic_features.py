#!/usr/bin/env python
"""
Filename: src/ASOkai/_pipeline/steps/analysis/intrinsic_features.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Definition of the intrinsic-features analysis step.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

from typing import Mapping

from ASOkai.Analysis import IntrinsicFeaturesAnalysis
from ASOkai._pipeline.contracts.file_types import CsvFile
from ASOkai._pipeline.contracts.files import FileInput, FileOutput
from ASOkai._pipeline.contracts.paths import (
    OutputPathTemplate,
    TemplateField,
)
from ASOkai._pipeline.contracts.parameters import ScalarParam
from ASOkai._pipeline.contracts.step_spec import StepSpec
from ASOkai._pipeline.steps.analysis.table.base import TableAnalysisStep
from ASOkai._pipeline.steps.core.create_target_gene import CreateTargetGeneStep


class IntrinsicFeaturesStep(TableAnalysisStep):
    name = "intrinsic-features"
    description = (
        "Computes nucleotide composition and CpG features for each " "target site."
    )
    analysis_cls = IntrinsicFeaturesAnalysis
    features_param = ScalarParam(
        "features",
        str,
        config="parameters.analysis.intrinsic_features.features",
        default="all",
        doc=(
            "Comma-separated intrinsic feature columns to calculate; "
            "'all' selects every feature."
        ),
    )
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
            "{target}_k{k}_{region}_intrinsic_{features}.csv",
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
                "features": TemplateField(
                    "parameters.analysis.intrinsic_features.features",
                    default="all",
                ),
            },
        ),
        doc="Intrinsic features per target site.",
    )
    spec = StepSpec(
        requirements={
            "WorkReuse": {"enableReuse": True},
        },
        params=[features_param],
        inputs=[target_gene_input],
        outputs=[intrinsic_features_output],
    )

    @staticmethod
    def _features(value: str) -> list[str] | None:
        if value == "all":
            return None
        names = [name.strip() for name in value.split(",")]
        if not all(names):
            raise ValueError("features must name at least one feature column")
        if len(set(names)) != len(names):
            raise ValueError("features must not repeat a feature column")
        IntrinsicFeaturesAnalysis(features=names)
        return names

    def validate_parameters(self, values: Mapping[str, object]) -> None:
        value = values["features"]
        if not isinstance(value, str):
            raise ValueError("features must be a comma-separated string")
        self._features(value)

    def analysis_kwargs(self, args):
        return {"features": self._features(args.features)}

    def analysis_units(self, args):
        return args.target_gene.sites
