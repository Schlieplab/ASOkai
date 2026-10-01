#!/usr/bin/env python
"""
Filename: src/ASOkai/_pipeline/steps/core/generate_aso_candidates.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Definition of the ASO-candidate generation step.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

import logging
from typing import Literal, Mapping, cast

from ASOkai.Antisense import AntisenseTherapeutic, Binding
from ASOkai._pipeline.contracts.file_types import JsonFile
from ASOkai._pipeline.contracts.files import FileInput, FileOutput
from ASOkai._pipeline.contracts.parameters import ScalarParam
from ASOkai._pipeline.contracts.paths import (
    OutputPathTemplate,
    TemplateField,
)
from ASOkai._pipeline.contracts.step_spec import StepSpec
from ASOkai._pipeline.steps.core.base import CoreStep
from ASOkai._pipeline.steps.core.create_target_gene import CreateTargetGeneStep

logger = logging.getLogger(__name__)


_ASO_PATH_FIELDS = {
    "assembly": TemplateField("parameters.genome.assembly_id"),
    "source": TemplateField("parameters.genome.source", default="ensembl"),
    "release": TemplateField("parameters.genome.ensembl_release"),
    "target": TemplateField.first_of(
        "parameters.target.target_id",
        "parameters.target.target_name",
    ),
    "k": TemplateField("parameters.target.k"),
    "region": TemplateField("parameters.target.region"),
    "design": TemplateField("parameters.antisense.design.type"),
    "left": TemplateField(
        "parameters.antisense.design.left_wing_length",
        default="na",
    ),
    "gap": TemplateField(
        "parameters.antisense.design.gap_length",
        default="na",
    ),
    "right": TemplateField(
        "parameters.antisense.design.right_wing_length",
        default="na",
    ),
    "mechanism": TemplateField("parameters.antisense.mechanism"),
}


class GenerateASOCandidatesStep(CoreStep):
    name = "generate-aso-candidates"
    description = "Generates ASO candidates for target sites."
    target_gene_input = FileInput(
        "target_gene",
        source=CreateTargetGeneStep.target_gene_output,
        doc="Serialized target gene object from create-target-gene.",
    )
    therapeutics_output = FileOutput(
        "therapeutics",
        file_type=JsonFile(list[AntisenseTherapeutic]),
        destination=OutputPathTemplate(
            "{assembly}/{source}/{release}/targets/{target}/antisense/"
            "{target}_k{k}_{region}_aso_{design}_"
            "l{left}_g{gap}_r{right}_{mechanism}_"
            "therapeutics.json",
            fields=_ASO_PATH_FIELDS,
        ),
        doc="Serialized ASO candidates.",
    )
    bindings_output = FileOutput(
        "bindings",
        file_type=JsonFile(list[Binding]),
        destination=OutputPathTemplate(
            "{assembly}/{source}/{release}/targets/{target}/antisense/"
            "{target}_k{k}_{region}_aso_{design}_"
            "l{left}_g{gap}_r{right}_{mechanism}_"
            "bindings.json",
            fields=_ASO_PATH_FIELDS,
        ),
        doc=(
            "Serialized relationships between therapeutic IDs and input "
            "target-site IDs."
        ),
    )
    spec = StepSpec(
        requirements={"WorkReuse": {"enableReuse": True}},
        params=[
            ScalarParam("k", int, config="parameters.target.k"),
            ScalarParam(
                "design",
                Literal["unmodified", "gapmer"],
                config="parameters.antisense.design.type",
            ),
            ScalarParam(
                "left_wing_length",
                int | None,
                config="parameters.antisense.design.left_wing_length",
                default=None,
            ),
            ScalarParam(
                "gap_length",
                int | None,
                config="parameters.antisense.design.gap_length",
                default=None,
            ),
            ScalarParam(
                "right_wing_length",
                int | None,
                config="parameters.antisense.design.right_wing_length",
                default=None,
            ),
            ScalarParam(
                "mechanism",
                str,
                config="parameters.antisense.mechanism",
            ),
        ],
        inputs=[target_gene_input],
        outputs=[therapeutics_output, bindings_output],
        compatible_with={"parameters.antisense.modality": ["aso"]},
    )

    def validate_parameters(self, values: Mapping[str, object]) -> None:
        """Require segment lengths appropriate for the selected ASO design."""
        mechanism_id = values.get("mechanism")
        if not isinstance(mechanism_id, str) or not mechanism_id.strip():
            raise ValueError("mechanism must be a non-empty string")
        design = values.get("design")
        length_names = (
            "left_wing_length",
            "gap_length",
            "right_wing_length",
        )
        lengths = tuple(values.get(name) for name in length_names)

        if design == "unmodified":
            if any(length is not None for length in lengths):
                raise ValueError(
                    "an unmodified design must not define gapmer segment " "lengths"
                )
            return

        if design != "gapmer":
            return
        if any(length is None for length in lengths):
            raise ValueError(
                "a gapmer design requires --left-wing-length, --gap-length, "
                "and --right-wing-length"
            )
        if any(type(length) is not int or length < 1 for length in lengths):
            raise ValueError("gapmer segment lengths must be positive integers")

        target_site_length = values.get("k")
        if type(target_site_length) is not int:
            return

        design_length = sum(cast(tuple[int, int, int], lengths))
        if design_length != target_site_length:
            raise ValueError(
                "gapmer segment lengths must equal the target-site length "
                f"({target_site_length}); received {design_length}"
            )

    def run_from_args(self, args) -> int:
        """Generate and serialize ASO candidates and their bindings."""
        from ASOkai.Antisense import (
            ASOCandidateGenerator,
            GapmerCandidateGenerator,
        )
        from ASOkai.Biochemistry import MechanismOfAction

        mechanism = MechanismOfAction(args.mechanism)
        if args.design == "unmodified":
            generator = ASOCandidateGenerator(mechanism=mechanism)
        elif args.design == "gapmer":
            generator = GapmerCandidateGenerator(
                mechanism=mechanism,
                left_wing_length=args.left_wing_length,
                gap_length=args.gap_length,
                right_wing_length=args.right_wing_length,
            )
        else:
            raise ValueError(f"Unsupported ASO design: {args.design!r}.")

        logger.info(
            "Generating %s candidates for %d target sites",
            args.design,
            len(args.target_gene.sites),
        )
        therapeutics, bindings = generator.generate(args.target_gene.sites)
        logger.info(
            "Generated %d therapeutics and %d bindings",
            len(therapeutics),
            len(bindings),
        )

        logger.info(
            "Writing therapeutics to %s",
            args.therapeutics_output,
        )
        self.therapeutics_output.write(
            args.therapeutics_output,
            therapeutics,
        )
        logger.info(
            "Writing bindings to %s",
            args.bindings_output,
        )
        self.bindings_output.write(
            args.bindings_output,
            bindings,
        )
        return 0
