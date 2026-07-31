"""Copyable starting point for an ASOkai analysis and pipeline step.

To add an analysis step:

1. Copy this file and replace the example analysis, names, and declarations.
2. Add any new configuration fields to ``config.schema.yaml`` and
   ``examples/config.example.yaml``.
3. Register the step in ``ASOkai.Plugins._registry``.
4. Run the contributor contract test, or let pre-commit run it.

The declared ``StepSpec`` is the step's schema; no second contributor schema is
needed.
"""

from ASOkai import Types
from ASOkai.Analysis import SiteSpecificAnalysis
from ASOkai.Plugins import (
    AnalysisStep,
    CsvFile,
    FileInput,
    FileOutput,
    OutputPathTemplate,
    ScalarParam,
    StepSpec,
    TemplateField,
)
from ASOkai._pipeline.steps.core.create_target_gene import (
    CreateTargetGeneStep,
)


class ExampleAnalysis(SiteSpecificAnalysis):
    """Replace this calculation with the new site-specific analysis."""

    def analyze(self, site) -> dict[str, Types.Scalar]:
        sequence = str(site.sequence or "")
        return {
            "example_value": float(len(sequence)),
        }


class ExampleAnalysisStep(AnalysisStep):
    """Replace the example names and declarations for the new step."""

    name = "example-analysis"
    description = "Calculates one example value for every target site."
    analysis_cls = ExampleAnalysis

    target_gene_input = FileInput(
        "target_gene",
        source=CreateTargetGeneStep.target_gene_output,
        override="target.target_gene_path",
    )
    analysis_output = FileOutput(
        "analysis",
        file_type=CsvFile(
            index={"site_id": str},
            columns={"example_value": float},
        ),
        destination=OutputPathTemplate(
            "{assembly}/targets/{target}/analysis/example/"
            "{target}_k{k}_{region}_example.csv",
            fields={
                "target": TemplateField.first_of(
                    "target_id",
                    "target_name",
                ),
            },
        ),
    )
    spec = StepSpec(
        params=[
            ScalarParam(
                "assembly",
                str,
                config="genome.assembly_id",
            ),
            ScalarParam(
                "target_id",
                str | None,
                config="target.target_id",
            ),
            ScalarParam(
                "target_name",
                str | None,
                config="target.target_name",
            ),
            ScalarParam("k", int, config="target.k"),
            ScalarParam(
                "region",
                Types.TargetRegion,
                config="target.region",
            ),
        ],
        inputs=[target_gene_input],
        outputs=[analysis_output],
    )

    def analysis_kwargs(self, args) -> dict:
        return {
            "sites": args.target_gene.sites,
        }
