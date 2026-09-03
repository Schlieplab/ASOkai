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

from ASOkai._pipeline.steps.base import Step
from ASOkai._pipeline.steps.core.create_target_gene import CreateTargetGeneStep
from ASOkai._pipeline.steps.core.download_genome import DownloadGenomeStep


class InstantiateTargetGeneTask:
    __slots__ = ()

    name: ClassVar[str] = "instantiate-target-gene"
    description: ClassVar[str] = (
        "Downloads genome data and creates the configured target gene."
    )
    steps: tuple[Step, ...] = (
        DownloadGenomeStep(),
        CreateTargetGeneStep(),
    )
