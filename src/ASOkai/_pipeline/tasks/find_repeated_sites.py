#!/usr/bin/env python
"""
Filename: src/ASOkai/_pipeline/tasks/find_repeated_sites.py
Authors: Arash Ayat, Kian Jalilian
Copyright: 2026, Alexander Schliep
Description: Task that searches potential repeated sites of a target gene.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

from typing import ClassVar

from ASOkai._pipeline.contracts.run_spec import FromRun, RunSpec
from ASOkai._pipeline.steps.analysis.identify_potential_repeated_sites import (
    IdentifyPotentialRepeatedSitesStep,
)
from ASOkai._pipeline.steps.core.create_target_gene import CreateTargetGeneStep
from ASOkai._pipeline.steps.utils.build_bowtie2_index import BuildBowtie2IndexStep
from ASOkai._pipeline.tasks.base import Task


class FindRepeatedSitesTask(Task):
    __slots__ = ()

    name: ClassVar[str] = "find-repeated-sites"
    description: ClassVar[str] = (
        "Builds a target-gene index and searches potential repeated sites."
    )
    category: ClassVar[str] = "analysis"
    runs = (
        RunSpec("gene", CreateTargetGeneStep()),
        RunSpec(
            "index",
            BuildBowtie2IndexStep(),
            inputs={"reference": FromRun("gene", "fasta")},
        ),
        RunSpec(
            "search",
            IdentifyPotentialRepeatedSitesStep(),
            inputs={"target_gene": FromRun("gene", "target_gene")},
        ),
    )
    outputs = {
        "index": FromRun("index", "index"),
        "potential_repeated_sites": FromRun(
            "search",
            "potential_repeated_sites",
        ),
    }
