#!/usr/bin/env python
"""
Filename: src/ASOkai/_pipeline/steps/core/generate_antisense_candidates.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Version: 0.1.1
Description: Definition of the antisense-candidate generation step.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

from typing import Literal

from ASOkai.Types import TargetRegion
from ASOkai._pipeline.file_types import JsonFile
from ASOkai._pipeline.files import FileInput, FileOutput
from ASOkai._pipeline.parameters import ScalarParam
from ASOkai._pipeline.paths import OutputPathTemplate, TemplateField
from ASOkai._pipeline.step_spec import StepSpec
from ASOkai._pipeline.steps.core.base import CoreStep
from ASOkai._pipeline.steps.core.create_target_gene import CreateTargetGeneStep


class GenerateAntisenseCandidatesStep(CoreStep):
    name = "generate-antisense-candidates"
    description = "Generates antisense therapeutic candidates for target sites."
    target_gene_input = FileInput(
        "target_gene",
        source=CreateTargetGeneStep.target_gene_output,
        override="target.target_gene_path",
        doc="Serialized target gene object from create-target-gene.",
    )
    therapeutics_output = FileOutput(
        "therapeutics",
        file_type=JsonFile(),
        destination=OutputPathTemplate(
            "{assembly}/targets/{target}/antisense/"
            "{target}_k{k}_{region}_{modality}_{chemistry}_{layout}_"
            "{mechanism}_therapeutics.json",
            fields={
                "target": TemplateField.first_of("target_id", "target_name"),
            },
        ),
        doc="Serialized antisense therapeutic candidates.",
    )
    bindings_output = FileOutput(
        "bindings",
        file_type=JsonFile(),
        destination=OutputPathTemplate(
            "{assembly}/targets/{target}/antisense/"
            "{target}_k{k}_{region}_{modality}_{chemistry}_{layout}_"
            "{mechanism}_bindings.json",
            fields={
                "target": TemplateField.first_of("target_id", "target_name"),
            },
        ),
        doc="Serialized therapeutic-to-site bindings.",
    )
    spec = StepSpec(
        requirements={"WorkReuse": {"enableReuse": True}},
        params=[
            ScalarParam("assembly", str, config="genome.assembly_id"),
            ScalarParam("target_id", str | None, config="target.target_id"),
            ScalarParam("target_name", str | None, config="target.target_name"),
            ScalarParam("k", int, config="target.k"),
            ScalarParam("region", TargetRegion, config="target.region"),
            ScalarParam("modality", Literal["aso"], config="antisense.modality"),
            ScalarParam(
                "chemistry",
                Literal["gapmer"],
                config="antisense.chemistry.type",
            ),
            ScalarParam(
                "layout",
                str,
                config="antisense.chemistry.layout",
            ),
            ScalarParam(
                "mechanism",
                Literal["rnase-h1"],
                config="antisense.mechanism",
            ),
        ],
        inputs=[target_gene_input],
        outputs=[therapeutics_output, bindings_output],
    )

    def run_from_args(self, args) -> int:
        """Generate and serialize antisense candidates and their bindings."""
        from ASOkai.Antisense import ASOCandidateGenerator
        from ASOkai.Biochemistry import GapmerChemistry, RNaseH1Mechanism

        chemistry = GapmerChemistry(layout=args.layout)
        mechanism = RNaseH1Mechanism()
        generator = ASOCandidateGenerator(
            chemistry=chemistry,
            mechanism=mechanism,
        )
        therapeutics, bindings = generator.generate(args.target_gene)

        self.therapeutics_output.write(
            args.therapeutics_output,
            [therapeutic.to_dict() for therapeutic in therapeutics],
        )
        self.bindings_output.write(
            args.bindings_output,
            [binding.to_dict() for binding in bindings],
        )
        return 0
