#!/usr/bin/env python
"""
Filename: examples/plugins/example_analysis/src/asokai_example_analysis/analysis_step.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Example external per-unit analysis and its pipeline declaration.
License: LGPL-3.0-or-later

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

from typing import ClassVar

from ASOkai import Types
from ASOkai.Analysis import PerUnitAnalysis
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
from ASOkai.Sites import Site


class ExampleAnalysis(PerUnitAnalysis):
    """Report sequence length and whether it reaches a configured minimum.

    - **sequence_length**: Number of nucleotides in the target-site sequence.
    - **passes_minimum**: Whether the sequence reaches the configured minimum.
    """

    analysis_unit_type: ClassVar[Types.AnalysisUnitType] = "site"

    def __init__(self, minimum_length: int) -> None:
        self.minimum_length = minimum_length

    def analyze_unit(self, site: Site) -> list[dict[str, Types.Scalar]]:
        sequence_length = len(site.sequence)
        return [{
            "site_id": site.id,
            "sequence_length": sequence_length,
            "passes_minimum": sequence_length >= self.minimum_length,
        }]


class ExampleAnalysisStep(AnalysisStep):
    """Declare how ASOkai configures and runs the example analysis."""

    name = "example-sequence-length"
    description = "Reports the length of every target site."
    analysis_cls = ExampleAnalysis

    target_gene_input = FileInput(
        "target_gene",
        source=CreateTargetGeneStep.target_gene_output,
        doc="Target gene containing the sites to analyze.",
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
            "{assembly}/{source}/{release}/targets/{target}/"
            "analysis/example/"
            "{target}_k{k}_{region}_min{minimum_length}_sequence_lengths.csv",
            fields={
                "assembly": TemplateField("genome.assembly_id"),
                "source": TemplateField(
                    "genome.source",
                    default="ensembl",
                ),
                "release": TemplateField("genome.ensembl_release"),
                "target": TemplateField.first_of(
                    "target.target_id",
                    "target.target_name",
                ),
                "k": TemplateField("target.k"),
                "region": TemplateField("target.region"),
                "minimum_length": TemplateField(
                    "example_analysis.minimum_length"
                ),
            },
        ),
        doc="Sequence length and minimum-length result for each target site.",
    )
    spec = StepSpec(
        params=[
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
        return {"minimum_length": args.minimum_length}

    def analysis_units(self, args):
        return args.target_gene.sites
