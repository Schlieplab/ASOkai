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

from typing import ClassVar

from ASOkai._pipeline.base import Runnable
from ASOkai._pipeline.steps.analysis.intrinsic_features import (
    IntrinsicFeaturesStep,
)
from ASOkai._pipeline.steps.core.generate_antisense_candidates import (
    GenerateAntisenseCandidatesStep,
)
from ASOkai._pipeline.tasks.instantiate_target_gene import InstantiateTargetGeneTask


class StandardWorkflow:
    name: ClassVar[str] = "standard"
    description: ClassVar[str] = (
        "Full pipeline: genome download → target gene creation → antisense "
        "candidate generation → intrinsic features."
    )
    members: list[Runnable] = [
        InstantiateTargetGeneTask(),
        GenerateAntisenseCandidatesStep(),
        IntrinsicFeaturesStep(),
    ]
