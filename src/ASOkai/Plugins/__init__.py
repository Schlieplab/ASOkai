#!/usr/bin/env python
"""
Filename: src/ASOkai/Plugins/__init__.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Public contracts for ASOkai extension packages.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

from ASOkai._cwl.model import CwlToolArgument
from ASOkai._pipeline.contracts.file_types import CsvFile, FileType, JsonFile, KffFile
from ASOkai._pipeline.contracts.files import FileInput, FileOutput
from ASOkai._pipeline.contracts.parameters import ScalarParam
from ASOkai._pipeline.contracts.paths import (
    InputConfigField,
    OutputPathTemplate,
    TemplateField,
)
from ASOkai._pipeline.contracts.step_spec import StepSpec
from ASOkai._pipeline.base import Runnable
from ASOkai._pipeline.steps.analysis.base import AnalysisStep
from ASOkai._pipeline.steps.analysis.intrinsic_features import (
    IntrinsicFeaturesStep,
)
from ASOkai._pipeline.steps.base import Step
from ASOkai._pipeline.steps.core.build_genome_kmer_index import (
    BuildGenomeKmerIndexStep,
)
from ASOkai._pipeline.steps.core.base import CoreStep
from ASOkai._pipeline.steps.core.create_target_gene import CreateTargetGeneStep
from ASOkai._pipeline.steps.core.download_genome import DownloadGenomeStep
from ASOkai._pipeline.steps.core.generate_aso_candidates import (
    GenerateASOCandidatesStep,
)
from ASOkai._pipeline.tasks.base import Task
from ASOkai._pipeline.tasks.instantiate_target_gene import InstantiateTargetGeneTask
from ASOkai._pipeline.workflows.base import Workflow
from ASOkai._pipeline.workflows.standard import StandardWorkflow

__all__ = [
    "AnalysisStep",
    "BuildGenomeKmerIndexStep",
    "CoreStep",
    "CreateTargetGeneStep",
    "CwlToolArgument",
    "CsvFile",
    "DownloadGenomeStep",
    "FileInput",
    "FileOutput",
    "FileType",
    "GenerateASOCandidatesStep",
    "IntrinsicFeaturesStep",
    "InputConfigField",
    "InstantiateTargetGeneTask",
    "JsonFile",
    "KffFile",
    "OutputPathTemplate",
    "Runnable",
    "ScalarParam",
    "Step",
    "StepSpec",
    "StandardWorkflow",
    "Task",
    "TemplateField",
    "Workflow",
]
