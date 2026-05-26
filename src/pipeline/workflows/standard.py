"""
Filename: src/pipeline/workflows/standard.py
Description: Standard ASOkai workflow — full pipeline from genome download
             through intrinsic features analysis.
             CWL is generated at runtime from the constituent step definitions.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

from pathlib import Path

from pipeline.base import Runnable
from pipeline.steps.intrinsic_features import IntrinsicFeaturesStep
from pipeline.tasks.instantiate_target_gene import InstantiateTargetGeneTask


class StandardWorkflow:
    name = "standard"
    description = "Full pipeline: genome download → target gene creation → intrinsic features."
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
