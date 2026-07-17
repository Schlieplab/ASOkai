#!/usr/bin/env python
"""
Filename: src/ASOkai/_pipeline/steps/intrinsic_features.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Version: 0.1.1
Description: Definition and CLI entrypoint for the intrinsic-features step.
License: LGPL-3.0-or-later
"""
from __future__ import annotations

import argparse
import sys
from typing import ClassVar, Literal

from ASOkai.Analysis import IntrinsicFeaturesAnalysis
from ASOkai._cwl.spec import (
    TemplateField,
    OutputPathTemplate,
    InputParam,
    OutputParam,
    ScalarParam,
    StepSpec,
)
from ASOkai._pipeline.base import AnalysisStep


class IntrinsicFeaturesStep(AnalysisStep):
    name = "intrinsic-features"
    description = "Computes intrinsic features (GC content, T-runs, AT-runs) for each ASO target site."
    analysis_cls = IntrinsicFeaturesAnalysis
    cli_module = "ASOkai._pipeline.steps.intrinsic_features"
    dependencies: ClassVar[list[str]] = ["create-target-gene"]
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
                Literal["exonic_only", "pre-mrna", "transcriptomic"],
                config="target.region",
                doc="Target region type.",
            ),
        ],
        inputs=[
            InputParam(
                "target_gene",
                override="target.target_gene_path",
                doc="Serialized target gene object from create-target-gene.",
            ),
        ],
        outputs=[
            OutputParam(
                "intrinsic_features",
                temp_filename="intrinsic_features.json",
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
            ),
        ],
    )

    def load_analysis_inputs(self, args) -> dict:
        from ASOkai.Targets import TargetGene

        return {
            "target_gene": TargetGene.from_file(str(args.target_gene)),
        }

    def analysis_kwargs(self, args, inputs: dict) -> dict:
        return {
            "sites": inputs["target_gene"].sites,
        }

    def analysis_metadata(self, args, inputs: dict) -> dict:
        return {
            "analysis": self.name,
            "assembly": args.assembly,
            "target_id": args.target_id,
            "target_name": args.target_name,
            "k": args.k,
            "region": args.region,
        }


def _build_parser() -> argparse.ArgumentParser:
    return IntrinsicFeaturesStep().build_parser(
        description="Compute intrinsic features for ASO target sites.",
    )


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint called by CWL baseCommand: intrinsic-features."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    args.intrinsic_features_output.parent.mkdir(parents=True, exist_ok=True)

    if not args.target_id and not args.target_name:
        parser.error("Either --target-id or --target-name is required.")

    return IntrinsicFeaturesStep().run_from_args(args)


if __name__ == "__main__":
    sys.exit(main())
