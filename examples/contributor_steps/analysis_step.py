#!/usr/bin/env python
"""
Filename: examples/contributor_steps/analysis_step.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Copyable starting point for an ASOkai analysis and pipeline step.
License: LGPL-3.0-or-later

To add a table analysis step:

1. Copy this file and replace the example analysis, names, and declarations.
2. Add any new configuration fields to
   ``src/ASOkai/_pipeline/config.schema.yaml`` and
   ``examples/config.example.yaml``.
3. Register the step in ``ASOkai._pipeline.catalog``.
4. Run the contributor contract test, or let pre-commit run it.

The declared ``StepSpec`` is the step's schema; no second contributor schema is
needed.

The first declared output is the primary analysis CSV. A table step may declare more
CSV or JSON outputs after it and return their values from
``additional_output_values``.

Use ``StepSpec.compatible_with`` only when the analysis is biologically
restricted, for example
``compatible_with={"parameters.antisense.mechanism": ["rnase-h1"]}``. Omit it for an
analysis that applies regardless of modality, mechanism, or chemistry.

Most steps need no custom validation. Override ``validate_parameters`` only
for relationships between scalar parameters that the YAML schema cannot
express; the method receives values keyed by their ``ScalarParam`` names.
"""

from typing import ClassVar

from ASOkai.Types import AnalysisUnitType, Scalar
from ASOkai.Analysis import PerUnitAnalysis
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
from ASOkai._pipeline.steps.analysis.table.base import TableAnalysisStep
from ASOkai._pipeline.steps.core.create_target_gene import CreateTargetGeneStep


class ExampleAnalysis(PerUnitAnalysis):
    """Replace this calculation with the new target-context analysis.

    - **target_matches**: Number of equal sequences in the selected target.
    """

    analysis_unit_type: ClassVar[AnalysisUnitType] = "site"

    def __init__(self, target: TargetGene) -> None:
        self.target = target

    def analyze_unit(self, site: Site) -> list[dict[str, Scalar]]:
        # Add per-site analysis code here.
        return [
            {
                "site_id": site.id,
                "target_matches": sum(
                    target_site.sequence == site.sequence
                    for target_site in self.target.sites
                ),
            }
        ]


class ExampleAnalysisStep(TableAnalysisStep):
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
        doc=(
            "Target used for the target-wide comparison. Link a named "
            "producer run to select a different region from the main sites."
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
                "{assembly}/{source}/{release}/targets/{target_name}/"
                "analysis/example/"
                "{target_name}_k{k}_{sites_region}_against_"
                "{target_region}_example.csv"
            ),
            fields={
                "assembly": TemplateField("parameters.genome.assembly"),
                "source": TemplateField(
                    "parameters.genome.source",
                    default="ensembl",
                ),
                "release": TemplateField("parameters.genome.release"),
                "target_name": TemplateField.first_of(
                    "parameters.target.target_id",
                    "parameters.target.target_name",
                ),
                "k": TemplateField("parameters.target.k"),
                "sites_region": InputConfigField(
                    "sites",
                    "parameters.target.region",
                ),
                "target_region": InputConfigField(
                    "target",
                    "parameters.target.region",
                ),
            },
        ),
    )
    spec = StepSpec(
        inputs=[sites_input, target_input],
        outputs=[analysis_output],
    )

    def analysis_kwargs(self, args) -> dict:
        return {"target": args.target}

    def analysis_units(self, args):
        return args.sites.sites
