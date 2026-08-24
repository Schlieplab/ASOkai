#!/usr/bin/env python
"""
Filename: src/ASOkai/_pipeline/tasks/instantiate_target_gene.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Version: 0.1.1
Description: Task whose goal is creating the configured target gene.
License: LGPL-3.0-or-later
"""
from __future__ import annotations

from typing import ClassVar

from ASOkai._pipeline.steps.base import Step
from ASOkai._pipeline.steps.core.create_target_gene import CreateTargetGeneStep


class InstantiateTargetGeneTask:
    name: ClassVar[str] = "instantiate-target-gene"
    description: ClassVar[str] = (
        "Downloads genome data and creates the configured target gene."
    )
    steps: list[Step] = [
        CreateTargetGeneStep(),
    ]
