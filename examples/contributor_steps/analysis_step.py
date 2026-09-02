"""Copyable starting point for an ASOkai analysis and pipeline step.

To add an analysis step:

1. Copy this file and replace the example analysis, names, and declarations.
2. Add any new configuration fields to
   ``src/ASOkai/_pipeline/config.schema.yaml`` and
   ``examples/config.example.yaml``.
3. Register the step in ``ASOkai._pipeline.catalog``.
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

from collections.abc import Iterable

from ASOkai.Types import Scalar
from ASOkai.Analysis import TargetSpecificAnalysis
from ASOkai.Sites import Site
from ASOkai.Targets import TargetGene
from ASOkai._pipeline.contracts.file_types import CsvFile
from ASOkai._pipeline.contracts.files import FileInput, FileOutput
from ASOkai._pipeline.contracts.paths import (
    InputConfigField,
    OutputPathTemplate,
    TemplateField,
)
from ASOkai._pipeline.contracts.step_spec import StepSpec
from ASOkai._pipeline.steps.analysis.base import AnalysisStep
from ASOkai._pipeline.steps.core.create_target_gene import CreateTargetGeneStep


class ExampleAnalysis(TargetSpecificAnalysis):
    """Replace this calculation with the new target-context analysis.

    - **target_matches**: Number of equal sequences in the selected target.
    """

    def __init__(
        self,
        target: TargetGene,
        sites: Iterable[Site],
        **kwargs,
    ) -> None:
        super().__init__(target=target, sites=sites, **kwargs)
        # Add target-context initialization here.

    def analyze(self, site: Site) -> dict[str, Scalar]:
        # Add per-site analysis code here.
        return {
            "target_matches": sum(
                target_site.sequence == site.sequence
                for target_site in self.target.sites
            ),
        }


class ExampleAnalysisStep(AnalysisStep):
    """Replace the example names and declarations for the new step."""

    name = "example-analysis"
    description = "Compares every main target site with a selected target."
    analysis_cls = ExampleAnalysis

    sites_input = FileInput(
        "sites",
        source=CreateTargetGeneStep.target_gene_output,
        doc="Main target containing the sites to analyze.",
    )
    target_input = FileInput(
        "target",
        source=CreateTargetGeneStep.target_gene_output,
        configurable_parameters=("region",),
        doc=(
            "Target used for the target-wide comparison. Its region may be "
            "configured independently from the main sites."
        ),
    )
    analysis_output = FileOutput(
        "analysis",
        file_type=CsvFile(
            index={"site_id": str},
            columns={"target_matches": int},
        ),
        destination=OutputPathTemplate(
            template=(
                "{assembly}/genomes/{source}/{release}/{species}/"
                "targets/{target_name}/analysis/example/"
                "{target_name}_k{k}_{sites_region}_against_"
                "{target_region}_example.csv"
            ),
            fields={
                "assembly": TemplateField("genome.assembly_id"),
                "source": TemplateField(
                    "genome.source",
                    default="ensembl",
                ),
                "release": TemplateField("genome.ensembl_release"),
                "species": TemplateField("genome.species"),
                "target_name": TemplateField.first_of(
                    "target.target_id",
                    "target.target_name",
                ),
                "k": TemplateField("target.k"),
                "sites_region": TemplateField("target.region"),
                "target_region": InputConfigField(
                    "target",
                    "target.region",
                ),
            },
        ),
    )
    spec = StepSpec(
        inputs=[sites_input, target_input],
        outputs=[analysis_output],
    )

    def analysis_kwargs(self, args) -> dict:
        return {
            "sites": args.sites.sites,
            "target": args.target,
        }
