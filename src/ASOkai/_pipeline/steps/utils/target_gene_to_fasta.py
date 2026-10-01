#!/usr/bin/env python
"""
Filename: src/ASOkai/_pipeline/steps/utils/target_gene_to_fasta.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Convert a serialized target gene to a plain FASTA reference.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

from Bio import SeqIO
from Bio.SeqRecord import SeqRecord

from ASOkai._pipeline.contracts.file_types import FastaFile
from ASOkai._pipeline.contracts.files import FileInput, FileOutput
from ASOkai._pipeline.contracts.step_spec import StepSpec
from ASOkai._pipeline.steps.core.create_target_gene import CreateTargetGeneStep
from ASOkai._pipeline.steps.utils.base import UtilityStep


class TargetGeneToFastaStep(UtilityStep):
    """Write the full target-gene sequence as one FASTA record."""

    name = "target-gene-to-fasta"
    description = "Converts a target-gene JSON file to a plain FASTA reference."
    target_gene_input = FileInput(
        "target_gene",
        source=CreateTargetGeneStep.target_gene_output,
        doc="Serialized target gene from create-target-gene by default.",
    )
    fasta_output = FileOutput(
        "fasta",
        file_type=FastaFile(),
        destination="targets/target_gene.fa",
        doc="One FASTA record containing the target-gene sequence.",
    )
    spec = StepSpec(inputs=[target_gene_input], outputs=[fasta_output])

    def run_from_args(self, args) -> int:
        """Deserialize the target gene and write its sequence in FASTA format."""
        target_gene = args.target_gene
        record = SeqRecord(
            target_gene.sequence,
            id=target_gene.id,
            description=target_gene.name,
        )
        with args.fasta_output.open("w", encoding="utf-8") as stream:
            SeqIO.write(record, stream, "fasta")
        return 0
