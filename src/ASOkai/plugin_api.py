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

from ASOkai._cwl.model import CwlToolArgument
from ASOkai._pipeline.contracts.file_types import CsvFile, FileType, JsonFile
from ASOkai._pipeline.contracts.files import FileInput, FileOutput
from ASOkai._pipeline.contracts.parameters import ScalarParam
from ASOkai._pipeline.contracts.paths import (
    OutputPathTemplate,
    TemplateField,
)
from ASOkai._pipeline.contracts.step_spec import StepSpec
from ASOkai._pipeline.base import Runnable
from ASOkai._pipeline.steps.analysis.base import AnalysisStep
from ASOkai._pipeline.steps.base import Step
from ASOkai._pipeline.steps.core.base import CoreStep
from ASOkai._pipeline.tasks.base import Task
from ASOkai._pipeline.workflows.base import Workflow

__all__ = [
    "AnalysisStep",
    "FileInput",
    "CoreStep",
    "CwlToolArgument",
    "CsvFile",
    "FileOutput",
    "FileType",
    "JsonFile",
    "OutputPathTemplate",
    "Runnable",
    "ScalarParam",
    "Step",
    "StepSpec",
    "Task",
    "TemplateField",
    "Workflow",
]
