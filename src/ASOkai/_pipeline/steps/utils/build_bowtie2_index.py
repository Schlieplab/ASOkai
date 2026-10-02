#!/usr/bin/env python
"""
Filename: src/ASOkai/_pipeline/steps/utils/build_bowtie2_index.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Reusable Bowtie 2 index builder for a supplied FASTA reference.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

from ASOkai.Utils import Bowtie2Build
from ASOkai._pipeline.contracts.file_types import (
    Bowtie2IndexDirectory,
    FastaFile,
)
from ASOkai._pipeline.contracts.files import FileInput, FileOutput
from ASOkai._pipeline.contracts.parameters import ScalarParam
from ASOkai._pipeline.contracts.paths import (
    OutputPathTemplate,
    TemplateField,
)
from ASOkai._pipeline.contracts.step_spec import StepSpec
from ASOkai._pipeline.steps.utils.base import UtilityStep


class BuildBowtie2IndexStep(UtilityStep):
    """Build a reusable Bowtie 2 index from any plain FASTA reference."""

    name = "build-bowtie2-index"
    description = "Builds a Bowtie 2 index directory from a FASTA reference."
    supports_multiple_threads = True
    reference_input = FileInput(
        "reference", file_type=FastaFile(), doc="Plain FASTA reference to index."
    )
    index_output = FileOutput(
        "index",
        file_type=Bowtie2IndexDirectory(),
        destination=OutputPathTemplate(
            "{assembly}/{source}/{release}/indexes/bowtie2/"
            "index.offrate{offrate}."
            "large{large}.packed{packed}",
            fields={
                "assembly": TemplateField(
                    "parameters.genome.assembly", default="external"
                ),
                "source": TemplateField(
                    "parameters.genome.source", default="user"
                ),
                "release": TemplateField(
                    "parameters.genome.release", default="na"
                ),
                "offrate": TemplateField(
                    "parameters.bowtie2.offrate", default="auto"
                ),
                "large": TemplateField(
                    "parameters.bowtie2.large_index", default=False
                ),
                "packed": TemplateField(
                    "parameters.bowtie2.packed", default=False
                ),
            },
        ),
        doc="Directory containing the six Bowtie 2 index files.",
    )
    spec = StepSpec(
        requirements={"WorkReuse": {"enableReuse": True}},
        params=[
            ScalarParam(
                "large_index",
                bool,
                config="parameters.bowtie2.large_index",
                doc="Force the large .bt2l index format.",
            ),
            ScalarParam(
                "offrate",
                int | None,
                config="parameters.bowtie2.offrate",
                default=None,
                doc="Suffix-array sampling rate.",
            ),
            ScalarParam(
                "packed",
                bool,
                config="parameters.bowtie2.packed",
                doc="Use packed representation while building.",
            ),
        ],
        inputs=[reference_input],
        outputs=[index_output],
    )

    def validate_parameters(self, values: Mapping[str, object]) -> None:
        """Validate builder options before invoking Bowtie 2."""
        offrate = values.get("offrate")
        if offrate is not None and (type(offrate) is not int or offrate < 0):
            raise ValueError("offrate must be a non-negative integer")

    def run_from_args(self, args) -> int:
        """Build the six-file index inside its declared output directory."""
        output = Path(args.index_output)
        output.mkdir(parents=True, exist_ok=True)
        Bowtie2Build().run(
            args.reference,
            Bowtie2IndexDirectory.index_base(output),
            threads=args.n_threads,
            large_index=args.large_index,
            offrate=args.offrate,
            packed=args.packed,
            quiet=True,
        )
        return 0
