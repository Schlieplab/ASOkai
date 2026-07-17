#!/usr/bin/env python
"""
Filename: src/ASOkai/_pipeline/tasks/instantiate_target_gene.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Version: 0.1.1
Description: Task that downloads genome files and creates the configured target gene.
License: LGPL-3.0-or-later
"""
from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from ASOkai._pipeline.base import Step
from ASOkai._pipeline.steps.create_target_gene import CreateTargetGeneStep
from ASOkai._pipeline.steps.download_genome import DownloadGenomeStep


class InstantiateTargetGeneTask:
    name: ClassVar[str] = "instantiate-target-gene"
    description: ClassVar[str] = (
        "Downloads genome data and creates the configured target gene."
    )
    steps: list[Step] = [
        DownloadGenomeStep(),
        CreateTargetGeneStep(),
    ]

    def output_paths(self, config: dict) -> dict[str, Path]:
        paths = {}
        paths.update(DownloadGenomeStep().output_paths(config))
        paths.update(CreateTargetGeneStep().output_paths(config))
        return paths

    def outputs_exist(self, config: dict) -> bool:
        return all(p.exists() for p in self.output_paths(config).values())

    def cleanup(self, config: dict) -> None:
        for step in self.steps:
            step.cleanup(config)
