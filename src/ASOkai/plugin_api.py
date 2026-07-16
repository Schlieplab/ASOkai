#!/usr/bin/env python
"""
Filename: src/ASOkai/plugin_api.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Version: 0.1.1
Description: Public plugin contracts for ASOkai extension packages.
License: LGPL-3.0-or-later
"""
from __future__ import annotations

from ASOkai._cwl.spec import (
    CwlToolArgument,
    InputParam,
    OutputParam,
    OutputPathTemplate,
    ScalarParam,
    StepSpec,
    TemplateField,
)
from ASOkai._pipeline.base import (
    AnalysisStep,
    CoreStep,
    Runnable,
    Step,
    Task,
    Workflow,
)

__all__ = [
    "AnalysisStep",
    "CoreStep",
    "CwlToolArgument",
    "InputParam",
    "OutputParam",
    "OutputPathTemplate",
    "Runnable",
    "ScalarParam",
    "Step",
    "StepSpec",
    "Task",
    "TemplateField",
    "Workflow",
]
