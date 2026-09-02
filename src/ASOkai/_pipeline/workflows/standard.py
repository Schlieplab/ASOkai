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
from ASOkai._pipeline.steps.core.generate_aso_candidates import (
    GenerateASOCandidatesStep,
)
from ASOkai._pipeline.tasks.instantiate_target_gene import InstantiateTargetGeneTask


class StandardWorkflow:
    __slots__ = ()

    name: ClassVar[str] = "standard"
    description: ClassVar[str] = (
        "Standard pipeline for Antisense therapeutics Design."
    )
    members: tuple[Runnable, ...] = (
        InstantiateTargetGeneTask(),
        GenerateASOCandidatesStep(),
        IntrinsicFeaturesStep(),
    )
