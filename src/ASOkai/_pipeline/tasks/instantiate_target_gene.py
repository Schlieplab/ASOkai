#!/usr/bin/env python
"""
Filename: src/ASOkai/_pipeline/tasks/instantiate_target_gene.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Task that downloads genome files and creates the configured target gene.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

from typing import ClassVar

from ASOkai._pipeline.contracts.run_spec import FromRun, RunSpec
from ASOkai._pipeline.steps.core.create_target_gene import CreateTargetGeneStep
from ASOkai._pipeline.steps.core.download_genome import DownloadGenomeStep
from ASOkai._pipeline.tasks.base import Task


class InstantiateTargetGeneTask(Task):
    __slots__ = ()

    name: ClassVar[str] = "instantiate-target-gene"
    category: ClassVar[str] = "core"
    description: ClassVar[str] = (
        "Downloads genome data and creates the configured target gene."
    )
    runs = (
        RunSpec("genome", DownloadGenomeStep()),
        RunSpec(
            "gene",
            CreateTargetGeneStep(),
            inputs={
                name: FromRun("genome", name)
                for name in ("dna", "cdna", "annotation", "db")
            },
        ),
    )
    outputs = {"target_gene": FromRun("gene", "target_gene")}
