"""Example external site-specific analysis and its pipeline declaration.

The first declared output is the primary analysis CSV. Additional CSV or JSON
outputs can follow it and receive values from ``additional_output_values``.

Use ``StepSpec.compatible_with`` only when the analysis is biologically
restricted, for example
``compatible_with={"antisense.mechanism": ["rnase-h1"]}``. Omit it for an
analysis that applies regardless of modality, mechanism, or chemistry.

Most steps need no custom validation. Override ``validate_parameters`` only
for relationships between scalar parameters that the YAML schema cannot
express; the method receives values keyed by their ``ScalarParam`` names.
"""

from ASOkai import Types
from ASOkai.Analysis import SiteSpecificAnalysis
from ASOkai.Plugins import (
    AnalysisStep,
    CreateTargetGeneStep,
    CsvFile,
    FileInput,
    FileOutput,
    OutputPathTemplate,
    ScalarParam,
    StepSpec,
    TemplateField,
)


class ExampleAnalysis(SiteSpecificAnalysis):
    """Report sequence length and whether it reaches a configured minimum."""

    def __init__(
        self,
        sites: list,
        minimum_length: int,
        n_processes: int = 1,
    ) -> None:
        super().__init__(sites, n_processes=n_processes)
        self.minimum_length = minimum_length

    def analyze(self, site) -> dict[str, Types.Scalar]:
        sequence_length = len(str(site.sequence or ""))
        return {
            "sequence_length": sequence_length,
            "passes_minimum": sequence_length >= self.minimum_length,
        }


class ExampleAnalysisStep(AnalysisStep):
    """Declare how ASOkai configures and runs the example analysis."""

    name = "example-sequence-length"
    description = "Reports the length of every target site."
    analysis_cls = ExampleAnalysis

    target_gene_input = FileInput(
        "target_gene",
        source=CreateTargetGeneStep.target_gene_output,
        override="target.target_gene_path",
    )
    sequence_lengths_output = FileOutput(
        "sequence_lengths",
        file_type=CsvFile(
            index={"site_id": str},
            columns={
                "sequence_length": int,
                "passes_minimum": bool,
            },
        ),
        destination=OutputPathTemplate(
            "{assembly}/targets/{target}/analysis/example/"
            "{target}_k{k}_{region}_sequence_lengths.csv",
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
            ScalarParam(
                "minimum_length",
                int,
                config="example_analysis.minimum_length",
            ),
        ],
        inputs=[target_gene_input],
        outputs=[sequence_lengths_output],
    )

    def analysis_kwargs(self, args) -> dict:
        return {
            "sites": args.target_gene.sites,
            "minimum_length": args.minimum_length,
        }
