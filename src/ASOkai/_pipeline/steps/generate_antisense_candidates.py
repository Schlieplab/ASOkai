#!/usr/bin/env python
"""Definition and CLI entrypoint for antisense candidate generation."""

from __future__ import annotations

import argparse
import json
import sys
from typing import ClassVar, Literal

from ASOkai.Types import TargetRegion
from ASOkai._cwl.spec import (
    InputParam,
    OutputParam,
    OutputPathTemplate,
    ScalarParam,
    StepSpec,
    TemplateField,
)
from ASOkai._pipeline.base import CoreStep


class GenerateAntisenseCandidatesStep(CoreStep):
    name = "generate-antisense-candidates"
    description = "Generates antisense therapeutic candidates for target sites."
    cli_module = "ASOkai._pipeline.steps.generate_antisense_candidates"
    dependencies: ClassVar[list[str]] = ["create-target-gene"]
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
        inputs=[
            InputParam(
                "target_gene",
                override="target.target_gene_path",
                doc="Serialized target gene object from create-target-gene.",
            ),
        ],
        outputs=[
            OutputParam(
                "therapeutics",
                temp_filename="therapeutics.json",
                destination=OutputPathTemplate(
                    "{assembly}/targets/{target}/antisense/"
                    "{target}_k{k}_{region}_{modality}_{chemistry}_{layout}_"
                    "{mechanism}_therapeutics.json",
                    fields={
                        "target": TemplateField.first_of("target_id", "target_name"),
                    },
                ),
                doc="Serialized antisense therapeutic candidates.",
            ),
            OutputParam(
                "bindings",
                temp_filename="bindings.json",
                destination=OutputPathTemplate(
                    "{assembly}/targets/{target}/antisense/"
                    "{target}_k{k}_{region}_{modality}_{chemistry}_{layout}_"
                    "{mechanism}_bindings.json",
                    fields={
                        "target": TemplateField.first_of("target_id", "target_name"),
                    },
                ),
                doc="Serialized therapeutic-to-site bindings.",
            ),
        ],
    )


def _build_parser() -> argparse.ArgumentParser:
    return GenerateAntisenseCandidatesStep().build_parser()


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if not args.target_id and not args.target_name:
        parser.error("Either --target-id or --target-name is required.")

    from ASOkai.Antisense import ASOCandidateGenerator
    from ASOkai.Biochemistry import GapmerChemistry, RNaseH1Mechanism
    from ASOkai.Targets import TargetGene

    target = TargetGene.from_file(str(args.target_gene))
    if not isinstance(target, TargetGene):
        raise TypeError("The target gene file does not contain a TargetGene.")
    chemistry = GapmerChemistry(layout=args.layout)
    mechanism = RNaseH1Mechanism()
    generator = ASOCandidateGenerator(
        chemistry=chemistry,
        mechanism=mechanism,
    )
    therapeutics, bindings = generator.generate(target)

    args.therapeutics_output.parent.mkdir(parents=True, exist_ok=True)
    args.bindings_output.parent.mkdir(parents=True, exist_ok=True)
    args.therapeutics_output.write_text(
        json.dumps([therapeutic.to_dict() for therapeutic in therapeutics], indent=4)
    )
    args.bindings_output.write_text(
        json.dumps([binding.to_dict() for binding in bindings], indent=4)
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
