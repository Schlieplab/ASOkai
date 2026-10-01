#!/usr/bin/env python
"""
Filename: src/ASOkai/_pipeline/tasks/index_target_gene.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Task that builds a Bowtie 2 index of a supplied target gene.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

from typing import ClassVar

from ASOkai._pipeline.contracts.run_spec import FromRun, RunSpec
from ASOkai._pipeline.steps.utils.build_bowtie2_index import BuildBowtie2IndexStep
from ASOkai._pipeline.steps.utils.target_gene_to_fasta import TargetGeneToFastaStep
from ASOkai._pipeline.tasks.base import Task


class IndexTargetGeneTask(Task):
    __slots__ = ()

    name: ClassVar[str] = "index-target-gene"
    description: ClassVar[str] = (
        "Converts a supplied target gene to FASTA and builds a Bowtie 2 index."
    )
    runs = (
        RunSpec("fasta", TargetGeneToFastaStep()),
        RunSpec(
            "index",
            BuildBowtie2IndexStep(),
            inputs={"reference": FromRun("fasta", "fasta")},
        ),
    )
    outputs = {
        "fasta": FromRun("fasta", "fasta"),
        "index": FromRun("index", "index"),
    }
