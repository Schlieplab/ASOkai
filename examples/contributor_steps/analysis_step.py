"""Copyable starting point for an ASOkai analysis and pipeline step.

To add an analysis step:

1. Copy this file and replace the example analysis, names, and declarations.
2. Add any new configuration fields to
   ``src/ASOkai/_pipeline/config.schema.yaml`` and
   ``examples/config.example.yaml``.
3. Register the step in ``ASOkai.Plugins._registry``.
4. Run the contributor contract test, or let pre-commit run it.

The declared ``StepSpec`` is the step's schema; no second contributor schema is
needed.

The first declared output is the primary analysis CSV. A step may declare more
CSV or JSON outputs after it and return their values from
``additional_output_values``.

Use ``StepSpec.compatible_with`` only when the analysis is biologically
restricted, for example
``compatible_with={"antisense.mechanism": ["rnase-h1"]}``. Omit it for an
analysis that applies regardless of modality, mechanism, or chemistry.

Most steps need no custom validation. Override ``validate_parameters`` only
for relationships between scalar parameters that the YAML schema cannot
express; the method receives values keyed by their ``ScalarParam`` names.
"""

from ASOkai._types import Scalar, TargetRegion
from ASOkai.Analysis import SiteSpecificAnalysis
from ASOkai._pipeline.contracts.file_types import CsvFile
from ASOkai._pipeline.contracts.files import FileInput, FileOutput
from ASOkai._pipeline.contracts.parameters import ScalarParam
from ASOkai._pipeline.contracts.paths import (
    OutputPathTemplate,
    TemplateField,
)
from ASOkai._pipeline.contracts.step_spec import StepSpec
from ASOkai._pipeline.steps.analysis.base import AnalysisStep
from ASOkai._pipeline.steps.core.create_target_gene import CreateTargetGeneStep


class ExampleAnalysis(SiteSpecificAnalysis):
    """Replace this calculation with the new site-specific analysis."""

    def __init__(self, sites: list, **kwargs) -> None:
        super().__init__(sites, **kwargs)
        # Add analysis-specific initialization here.

    def analyze(self, site) -> dict[str, Scalar]:
        # Add per-site analysis code here.
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
    )
    analysis_output = FileOutput(
        "analysis",
        file_type=CsvFile(
            index={"site_id": str},
            columns={"example_value": float},
        ),
        destination=OutputPathTemplate(
            template=(
                "{assembly}/targets/{target}/analysis/example/"
                "{target}_k{k}_{region}_example.csv"
            ),
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
                TargetRegion,
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
