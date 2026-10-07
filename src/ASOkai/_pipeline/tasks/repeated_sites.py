#!/usr/bin/env python
"""
Filename: src/ASOkai/_pipeline/tasks/repeated_sites.py
Author: Kian Jalilian
Copyright: 2026, Alexander Schliep
Description: Task that finds where the target sites of a target gene repeat.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

from typing import ClassVar

from ASOkai._pipeline.contracts.run_spec import FromRun, RunSpec
from ASOkai._pipeline.steps.analysis.count_genomic_hits import CountGenomicHitsStep
from ASOkai._pipeline.steps.analysis.treesearch_target_sites import (
    TreesearchTargetSitesStep,
)
from ASOkai._pipeline.steps.core.create_target_gene import CreateTargetGeneStep
from ASOkai._pipeline.steps.utils.build_bowtie2_index import BuildBowtie2IndexStep
from ASOkai._pipeline.steps.utils.query_bowtie2 import QueryBowtie2Step
from ASOkai._pipeline.tasks.base import Task


class RepeatedSitesTask(Task):
    __slots__ = ()

    name: ClassVar[str] = "repeated-sites"
    description: ClassVar[str] = (
        "Aligns target-site queries to the target gene and counts repeated sites."
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
            "treesearch",
            TreesearchTargetSitesStep(),
            inputs={"target_gene": FromRun("gene", "target_gene")},
        ),
        RunSpec(
            "query",
            QueryBowtie2Step(),
            inputs={
                "index": FromRun("index", "index"),
                "queries": FromRun("treesearch", "candidate_repeated_sites"),
            },
        ),
        RunSpec(
            "analysis",
            CountGenomicHitsStep(),
            inputs={
                "target_gene": FromRun("gene", "target_gene"),
                "alignments": FromRun("query", "alignments"),
            },
        ),
    )
    outputs = {
        "candidate_repeated_sites": FromRun(
            "treesearch",
            "candidate_repeated_sites",
        ),
        "alignments": FromRun("query", "alignments"),
        "repeated_sites": FromRun("analysis", "hit_counts"),
        "genomic_sites": FromRun("analysis", "genomic_sites"),
    }
