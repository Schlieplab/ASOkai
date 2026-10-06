#!/usr/bin/env python
"""
Filename: tests/unit/test_target_gene_index_pipeline.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Tests for target-gene FASTA links and Bowtie 2 indexing.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from ASOkai._pipeline import catalog
from ASOkai._pipeline.contracts.execution import (
    StepInputBinding,
    StepRun,
    StepRunOutput,
)
from ASOkai._pipeline.contracts.file_types import Bowtie2IndexDirectory
from ASOkai._pipeline.output_receipts import (
    receipt_path,
    record_validated_outputs,
    reusable_output_paths,
)
from ASOkai._pipeline.plan import build_plan
from ASOkai._pipeline.steps.core.create_target_gene import CreateTargetGeneStep
from ASOkai._pipeline.steps.utils import build_bowtie2_index
from ASOkai._pipeline.steps.utils.build_bowtie2_index import BuildBowtie2IndexStep
from ASOkai._pipeline.steps.utils.build_kmc_index import BuildKMCIndexStep


@pytest.fixture
def config(tmp_path: Path) -> dict:
    return {
        "datadir": str(tmp_path),
        "parameters": {
            "genome": {
                "assembly": "GRCh38",
                "release": 114,
                "species": "Homo_sapiens",
            },
            "target": {
                "target_id": "ENSG00000133703",
                "k": 16,
                "region": "pre-mrna",
            },
        },
    }


def _gene_run(config: dict, tmp_path: Path, **parameters: object) -> StepRun:
    step = CreateTargetGeneStep()
    return StepRun(
        "gene",
        step,
        config,
        parameters=parameters,
        inputs=tuple(
            StepInputBinding(item, tmp_path / item.name)
            for item in step.spec.inputs
        ),
    )


def test_target_parameter_flows_through_gene_fasta_to_kmc(
    config: dict, tmp_path: Path
) -> None:
    config["parameters"]["genome"]["source"] = "ensembl"
    gene = _gene_run(config, tmp_path, k=18)
    kmc_step = BuildKMCIndexStep()
    index = StepRun(
        "index",
        kmc_step,
        config,
        inputs=(
            StepInputBinding(
                kmc_step.reference_input,
                gene.output(CreateTargetGeneStep.fasta_output),
            ),
        ),
    )

    assert config["parameters"]["target"]["k"] == 16
    assert gene.config["parameters"]["target"]["k"] == 18
    assert index.parameters["k"] == 18
    assert index.output_paths()["kmc_index"].name.startswith("index.k18.")


def test_bowtie2_builder_names_options_and_forwards_them(
    config: dict, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    builder = MagicMock()
    monkeypatch.setattr(build_bowtie2_index, "Bowtie2Build", lambda: builder)
    monkeypatch.setattr(Bowtie2IndexDirectory, "validate", lambda self, path: None)
    step = BuildBowtie2IndexStep()
    reference = tmp_path / "reference.fa"
    reference.write_text(">test\nACGT\n")
    run = StepRun(
        "index",
        step,
        config,
        parameters={"offrate": 3, "packed": True},
        inputs=(StepInputBinding(step.reference_input, reference),),
    )
    output = run.output_paths()["index"]
    assert output.name == "index.offrate3.largeFalse.packedTrue"

    assert step.run_cli(
        [
            "--reference", str(reference),
            "--index-output", str(output),
            "--n-threads", "2",
            "--offrate", "3",
            "--packed",
        ]
    ) == 0
    builder.run.assert_called_once_with(
        reference,
        output / "index",
        threads=2,
        large_index=False,
        offrate=3,
        packed=True,
        quiet=True,
    )


def test_generic_builder_uses_stable_filename(tmp_path: Path) -> None:
    step = BuildBowtie2IndexStep()
    config = {
        "datadir": str(tmp_path),
        "parameters": {},
    }
    run = StepRun(
        "index",
        step,
        config,
        inputs=(StepInputBinding(step.reference_input, tmp_path / "other.fa"),),
    )
    assert run.output_paths()["index"] == (
        tmp_path / "external/user/na/indexes/bowtie2/"
        "index.offrateauto.largeFalse.packedFalse"
    )


def test_changed_reference_invalidates_index_receipt(tmp_path: Path) -> None:
    first_reference = tmp_path / "first.fa"
    second_reference = tmp_path / "second.fa"
    first_reference.write_text(">first\nACGT\n")
    second_reference.write_text(">second\nTGCA\n")
    step = BuildBowtie2IndexStep()
    config = {"datadir": str(tmp_path)}
    first = StepRun(
        "first",
        step,
        config,
        inputs=(StepInputBinding(step.reference_input, first_reference),),
    )
    second = StepRun(
        "second",
        step,
        config,
        inputs=(StepInputBinding(step.reference_input, second_reference),),
    )
    first.output_paths()["index"].mkdir(parents=True)
    record_validated_outputs(first)

    assert first.output_paths() == second.output_paths()
    assert receipt_path(first) == receipt_path(second)
    assert reusable_output_paths(second) is None


def test_gene_override_invalidates_downstream_index_receipt(
    config: dict, tmp_path: Path
) -> None:
    for file_input in CreateTargetGeneStep.spec.inputs:
        (tmp_path / file_input.name).write_text("input")

    def index_for_region(region: str) -> StepRun:
        gene = _gene_run(config, tmp_path, region=region)
        step = BuildBowtie2IndexStep()
        return StepRun(
            "index",
            step,
            config,
            inputs=(
                StepInputBinding(
                    step.reference_input,
                    gene.output(CreateTargetGeneStep.fasta_output),
                ),
            ),
        )

    first = index_for_region("pre-mrna")
    second = index_for_region("exonic")
    first.output_paths()["index"].mkdir(parents=True)
    record_validated_outputs(first)

    assert first.input_paths() != second.input_paths()
    assert first.output_paths() == second.output_paths()
    assert receipt_path(first) == receipt_path(second)
    assert reusable_output_paths(second) is None


def test_builder_registered_without_conversion_step() -> None:
    pipeline_catalog = catalog.get_pipeline_catalog()
    assert "index-target-gene" not in pipeline_catalog.tasks
    assert "build-bowtie2-index" in pipeline_catalog.steps
    assert "target-gene-to-fasta" not in pipeline_catalog.steps


def test_gene_fasta_can_feed_bowtie_builder(config: dict) -> None:
    config["runs"] = [
        {"step": "create-target-gene", "id": "target_gene"},
        {
            "step": "build-bowtie2-index",
            "id": "index",
            "inputs": {"reference": {"from": "run.target_gene.fasta"}},
        },
    ]
    plan = build_plan(
        [],
        config,
        _registry=catalog.get_pipeline_catalog().steps,
    )

    index = next(run for run in plan.runs_to_execute if run.run_id == "runs.index")
    source = index.inputs[0].source
    assert isinstance(source, StepRunOutput)
    assert source.run.step.name == "create-target-gene"
    assert source.output.name == "fasta"
    assert index.input_paths()["reference"] == source.run.output_paths()["fasta"]


def test_task_fasta_alias_can_feed_bowtie_builder(config: dict) -> None:
    config["runs"] = [
        {"task": "instantiate-target-gene", "id": "target_gene"},
        {
            "step": "build-bowtie2-index",
            "id": "index",
            "inputs": {"reference": {"from": "run.target_gene.fasta"}},
        },
    ]
    plan = build_plan(
        [],
        config,
        _registry=catalog.get_pipeline_catalog().steps,
    )

    index = next(run for run in plan.runs_to_execute if run.run_id == "runs.index")
    source = index.inputs[0].source
    assert isinstance(source, StepRunOutput)
    assert source.run.run_id == "runs.target_gene.gene"
    assert source.output is CreateTargetGeneStep.fasta_output
