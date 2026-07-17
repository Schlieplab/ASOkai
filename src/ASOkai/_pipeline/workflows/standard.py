#!/usr/bin/env python
"""
Filename: src/ASOkai/_pipeline/workflows/standard.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Version: 0.1.1
Description: Defines the standard ASOkai workflow from genome download through intrinsic features.
License: LGPL-3.0-or-later
"""
from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from ASOkai._pipeline.base import Runnable
from ASOkai._pipeline.steps.intrinsic_features import IntrinsicFeaturesStep
from ASOkai._pipeline.tasks.instantiate_target_gene import InstantiateTargetGeneTask


class StandardWorkflow:
    name: ClassVar[str] = "standard"
    description: ClassVar[str] = (
        "Full pipeline: genome download → target gene creation → intrinsic features."
    )
    members: list[Runnable] = [
        InstantiateTargetGeneTask(),
        IntrinsicFeaturesStep(),
    ]

    def output_paths(self, config: dict) -> dict[str, Path]:
        paths = {}
        paths.update(InstantiateTargetGeneTask().output_paths(config))
        paths.update(IntrinsicFeaturesStep().output_paths(config))
        return paths

    def outputs_exist(self, config: dict) -> bool:
        return all(p.exists() for p in self.output_paths(config).values())

    def cleanup(self, config: dict) -> None:
        for p in self.output_paths(config).values():
            if p.exists():
                p.unlink()
