#!/usr/bin/env python
"""
Filename: tests/unit/test_target_gene_index_pipeline.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Tests for target-gene FASTA conversion and Bowtie 2 indexing.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from unittest.mock import MagicMock

from Bio import SeqIO
from Bio.Seq import Seq
import pytest

from ASOkai.Targets import TargetGene
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
from ASOkai._pipeline.steps.utils.target_gene_to_fasta import TargetGeneToFastaStep
from ASOkai._pipeline.tasks.index_target_gene import IndexTargetGeneTask
from ASOkai._pipeline.tasks.base import validate_task_runs


@pytest.fixture
def config(tmp_path: Path) -> dict:
    return {
        "datadir": str(tmp_path),
        "parameters": {
            "genome": {
                "assembly_id": "GRCh38",
                "ensembl_release": 114,
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


def _fasta_run(config: dict, producer: StepRun) -> StepRun:
    step = TargetGeneToFastaStep()
    return StepRun(
        "fasta",
        step,
        config,
        inputs=(
            StepInputBinding(
                step.target_gene_input,
                producer.output(producer.step.target_gene_output),
            ),
        ),
    )


def test_fasta_conversion_uses_full_target_sequence(tmp_path: Path) -> None:
    gene = TargetGene(
        id="ENSG00000133703",
        name="KRAS",
        chr="12",
        start=1,
        end=8,
        strand="+",
        sequence=Seq("ACGTTGCA"),
        sites={},
    )
    source = tmp_path / "target.json"
    CreateTargetGeneStep.target_gene_output.write(source, gene)
    output = tmp_path / "target.fa"

    assert TargetGeneToFastaStep().run_cli(
        ["--target-gene", str(source), "--fasta-output", str(output)]
    ) == 0

    records = list(SeqIO.parse(output, "fasta"))
    assert len(records) == 1
    assert records[0].id == gene.id
    assert records[0].description == f"{gene.id} {gene.name}"
    assert records[0].seq == gene.sequence


def test_fasta_destination_keeps_stable_filename(
    config: dict, tmp_path: Path
) -> None:
    producer = _gene_run(config, tmp_path, region="exonic")
    fasta = _fasta_run(config, producer)

    assert fasta.output_paths()["fasta"] == tmp_path / "targets/target_gene.fa"

    name_config = deepcopy(config)
    name_config["parameters"]["target"] = {
        "target_name": "KRAS", "k": 16, "region": "pre-mrna"
    }
    named = _fasta_run(name_config, _gene_run(name_config, tmp_path))
    assert named.output_paths() == fasta.output_paths()


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
        fasta = _fasta_run(config, gene)
        step = BuildBowtie2IndexStep()
        return StepRun(
            "index",
            step,
            config,
            inputs=(
                StepInputBinding(
                    step.reference_input,
                    fasta.output(fasta.step.fasta_output),
                ),
            ),
        )

    first = index_for_region("pre-mrna")
    second = index_for_region("exonic")
    first.output_paths()["index"].mkdir(parents=True)
    record_validated_outputs(first)

    assert first.input_paths() == second.input_paths()
    assert first.output_paths() == second.output_paths()
    assert receipt_path(first) == receipt_path(second)
    assert reusable_output_paths(second) is None


def test_index_target_gene_task_wiring_and_registration() -> None:
    task = IndexTargetGeneTask()
    assert [run.run_id for run in validate_task_runs(task)] == ["fasta", "index"]
    assert (
        task.runs[0].step.target_gene_input.source
        is CreateTargetGeneStep.target_gene_output
    )
    assert set(task.outputs) == {"fasta", "index"}
    assert catalog.get_pipeline_catalog().tasks[task.name].name == task.name
    assert "build-bowtie2-index" in catalog.get_pipeline_catalog().steps
    assert "target-gene-to-fasta" in catalog.get_pipeline_catalog().steps


def test_index_target_gene_task_accepts_instantiation_output(
    config: dict,
) -> None:
    config["runs"] = [
        {"task": "instantiate-target-gene", "id": "gene"},
        {
            "task": "index-target-gene",
            "id": "indexing",
            "runs": [
                {
                    "id": "fasta",
                    "inputs": {
                        "target_gene": {"from": "run.gene.target_gene"}
                    },
                }
            ],
        },
    ]
    plan = build_plan([], config, _registry=catalog.get_pipeline_catalog().steps)
    runs = {run.run_id: run for run in plan.runs_to_execute}
    assert list(runs) == [
        "runs.gene.genome",
        "runs.gene.gene",
        "runs.indexing.fasta",
        "runs.indexing.index",
    ]
    assert runs["runs.indexing.fasta"].input_paths()["target_gene"] == runs[
        "runs.gene.gene"
    ].output_paths()["target_gene"]
    index = runs["runs.indexing.index"]
    assert index.input_paths()["reference"] == runs[
        "runs.indexing.fasta"
    ].output_paths()["fasta"]
    assert index.output_paths()["index"].name.startswith(
        "index.offrate"
    )


def test_fasta_step_uses_default_target_gene_producer(config: dict) -> None:
    plan = build_plan(
        [TargetGeneToFastaStep()],
        config,
        _registry=catalog.get_pipeline_catalog().steps,
    )

    source = plan.goals[0].inputs[0].source
    assert isinstance(source, StepRunOutput)
    assert source.run.step.name == "create-target-gene"
    assert source.run in plan.runs_to_execute


def test_index_target_gene_uses_default_target_gene_producer(config: dict) -> None:
    plan = build_plan(
        [IndexTargetGeneTask()],
        config,
        _registry=catalog.get_pipeline_catalog().steps,
    )

    assert [run.step.name for run in plan.runs_to_execute] == [
        "download-genome",
        "create-target-gene",
        "target-gene-to-fasta",
        "build-bowtie2-index",
    ]


def test_index_target_gene_accepts_existing_file(
    tmp_path: Path,
) -> None:
    path = tmp_path / "supplied_target.json"
    gene = TargetGene(
        id="ENSG00000133703",
        name="KRAS",
        chr="12",
        start=1,
        end=4,
        strand="+",
        sequence=Seq("ACGT"),
        sites={},
    )
    CreateTargetGeneStep.target_gene_output.write(path, gene)
    config = {
        "datadir": str(tmp_path),
        "runs": [
            {
                "task": "index-target-gene",
                "runs": [
                    {"id": "fasta", "inputs": {"target_gene": {"path": str(path)}}}
                ],
            }
        ],
    }
    plan = build_plan([], config, _registry=catalog.get_pipeline_catalog().steps)

    assert [run.step.name for run in plan.runs_to_execute] == [
        "target-gene-to-fasta",
        "build-bowtie2-index",
    ]
    assert plan.runs_to_execute[0].input_paths()["target_gene"] == path


def test_gene_child_override_keeps_index_destination(config: dict) -> None:
    config["runs"] = [
        {"task": "instantiate-target-gene", "id": "gene"},
        {
            "task": "index-target-gene",
            "id": "indexing",
            "runs": [
                {
                    "id": "fasta",
                    "inputs": {
                        "target_gene": {"from": "run.gene.target_gene"}
                    },
                }
            ],
        },
    ]
    original = build_plan([], config, _registry=catalog.get_pipeline_catalog().steps)
    original_index = next(
        run for run in original.runs_to_execute if run.run_id.endswith(".index")
    )
    config["runs"][0]["runs"] = [
        {"id": "gene", "parameters": {"region": "exonic"}}
    ]
    plan = build_plan(
        [],
        config,
        _registry=catalog.get_pipeline_catalog().steps,
    )
    index = next(
        run for run in plan.runs_to_execute
        if run.run_id.endswith(".index")
    )
    assert index.output_paths()["index"] == original_index.output_paths()["index"]
    filename = index.output_paths()["index"].name
    spec = index.cwl_spec()
    assert spec.outputs[0].glob == filename
    assert any(
        argument.prefix == "--index-output" and argument.value_from == filename
        for argument in spec.arguments
    )
