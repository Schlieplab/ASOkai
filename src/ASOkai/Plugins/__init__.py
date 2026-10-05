#!/usr/bin/env python
"""
Filename: src/ASOkai/Plugins/__init__.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Public contracts for ASOkai extension packages.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

from ASOkai._pipeline.contracts.file_types import (
    Bowtie2IndexDirectory,
    CsvFile,
    FastaFile,
    FileType,
    JsonFile,
    KffFile,
)
from ASOkai._pipeline.contracts.files import FileInput, FileOutput
from ASOkai._pipeline.contracts.parameters import ScalarParam
from ASOkai._pipeline.contracts.paths import (
    InputConfigField,
    OutputPathTemplate,
    TemplateField,
)
from ASOkai._pipeline.contracts.run_spec import FromRun, RunSpec
from ASOkai._pipeline.contracts.step_spec import StepSpec
from ASOkai._pipeline.base import Runnable
from ASOkai._pipeline.steps.analysis.base import AnalysisStep
from ASOkai._pipeline.steps.analysis.table.base import TableAnalysisStep
from ASOkai._pipeline.steps.analysis.intrinsic_features import (
    IntrinsicFeaturesStep,
)
from ASOkai._pipeline.steps.base import ExternalCommandStep, Step
from ASOkai._pipeline.steps.utils.build_bowtie2_index import BuildBowtie2IndexStep
from ASOkai._pipeline.steps.utils.build_kmc_index import BuildKMCIndexStep
from ASOkai._pipeline.steps.utils.target_gene_to_fasta import TargetGeneToFastaStep
from ASOkai._pipeline.steps.core.base import CoreStep
from ASOkai._pipeline.steps.utils.base import UtilityStep
from ASOkai._pipeline.steps.core.create_target_gene import CreateTargetGeneStep
from ASOkai._pipeline.steps.core.download_genome import DownloadGenomeStep
from ASOkai._pipeline.steps.core.generate_therapeutic_candidates import (
    GenerateTherapeuticCandidatesStep,
)
from ASOkai._pipeline.tasks.base import Task
from ASOkai._pipeline.tasks.index_target_gene import IndexTargetGeneTask
from ASOkai._pipeline.tasks.instantiate_target_gene import InstantiateTargetGeneTask
from ASOkai._pipeline.workflows.base import Workflow
from ASOkai._pipeline.workflows.standard import StandardWorkflow

__all__ = [
    "AnalysisStep",
    "BuildKMCIndexStep",
    "BuildBowtie2IndexStep",
    "Bowtie2IndexDirectory",
    "CoreStep",
    "CreateTargetGeneStep",
    "CsvFile",
    "DownloadGenomeStep",
    "ExternalCommandStep",
    "FileInput",
    "FileOutput",
    "FileType",
    "FastaFile",
    "GenerateTherapeuticCandidatesStep",
    "IntrinsicFeaturesStep",
    "InputConfigField",
    "IndexTargetGeneTask",
    "InstantiateTargetGeneTask",
    "JsonFile",
    "KffFile",
    "OutputPathTemplate",
    "Runnable",
    "RunSpec",
    "FromRun",
    "ScalarParam",
    "Step",
    "StepSpec",
    "StandardWorkflow",
    "Task",
    "TargetGeneToFastaStep",
    "TableAnalysisStep",
    "TemplateField",
    "UtilityStep",
    "Workflow",
]
