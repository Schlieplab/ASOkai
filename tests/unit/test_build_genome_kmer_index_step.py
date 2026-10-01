#!/usr/bin/env python
"""
Filename: tests/unit/test_build_genome_kmer_index_step.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Tests for BuildGenomeKmerIndexStep.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from ASOkai._cwl.generation import StepCwlGenerator, generate_cwl_bundle
from ASOkai._pipeline import config as cfg
from ASOkai._pipeline.contracts.execution import StepInputBinding, StepRun
from ASOkai._pipeline.contracts.file_types import KffFile
from ASOkai._pipeline.steps.core.build_genome_kmer_index import (
    BuildGenomeKmerIndexStep,
)
from ASOkai._pipeline.steps.core.download_genome import DownloadGenomeStep
from ASOkai.Plugins import CoreStep, Step


@pytest.fixture
def config(tmp_path: Path) -> dict:
    return {
        "datadir": str(tmp_path),
        "resources": {"build-genome-kmer-index": {"n_threads": 6}},
        "parameters": {
            "genome": {
                "assembly_id": "GRCh38",
                "ensembl_release": 114,
                "source": "ensembl",
                "species": "Homo_sapiens",
            },
            "target": {"k": 16},
        },
    }


@pytest.fixture
def step() -> BuildGenomeKmerIndexStep:
    return BuildGenomeKmerIndexStep()


def _run(step: BuildGenomeKmerIndexStep, config: dict, dna: Path) -> StepRun:
    return StepRun(
        step.name,
        step,
        config,
        inputs=(StepInputBinding(step.dna_input, dna),),
    )


def test_step_contract(step: BuildGenomeKmerIndexStep) -> None:
    assert isinstance(step, Step)
    assert isinstance(step, CoreStep)
    assert step.name == "build-genome-kmer-index"
    assert step.dependencies == ["download-genome"]
    assert step.dna_input.source is DownloadGenomeStep.dna_output
    assert isinstance(step.kmer_index_output.file_type, KffFile)
    assert step.config_map == {"k": "parameters.target.k"}
    assert step.supports_multiple_threads is True


def test_output_path_is_genome_scoped(
    step: BuildGenomeKmerIndexStep,
    config: dict,
    tmp_path: Path,
) -> None:
    output = _run(step, config, tmp_path / "dna.fa.gz").output_paths()["kmer_index"]

    assert output == (
        tmp_path
        / "GRCh38"
        / "ensembl"
        / "114"
        / "genome"
        / "indexes"
        / "kmc"
        / "GRCh38.k16.kff"
    )


def test_cwl_spec_exposes_runtime_resources(
    step: BuildGenomeKmerIndexStep,
    config: dict,
    tmp_path: Path,
) -> None:
    doc = yaml.safe_load(
        StepCwlGenerator().render(_run(step, config, tmp_path / "dna.fa.gz"))
    )

    assert set(doc["inputs"]) == {"k", "dna", "n_threads"}
    assert doc["inputs"]["n_threads"]["inputBinding"] == {"prefix": "--n-threads"}
    assert {
        "prefix": "--kmer-index-output",
        "valueFrom": "GRCh38.k16.kff",
    } in doc["arguments"]


def test_generated_workflow_passes_configured_resources(
    step: BuildGenomeKmerIndexStep,
    config: dict,
    tmp_path: Path,
) -> None:
    generated = generate_cwl_bundle([_run(step, config, tmp_path / "dna.fa.gz")])
    workflow = yaml.safe_load(generated.run_cwl)
    tool = yaml.safe_load(generated.step_cwls["build-genome-kmer-index.cwl"])

    step_inputs = workflow["steps"]["step_build_genome_kmer_index"]["in"]
    assert step_inputs["n_threads"] == {"default": 6}
    assert tool["requirements"]["ResourceRequirement"] == {
        "coresMin": 6,
        "ramMin": 4096,
    }


def test_run_cli_builds_one_kff_with_configured_resources(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from ASOkai._pipeline.contracts.file_types import kff
    from ASOkai._pipeline.steps.core import build_genome_kmer_index

    captured: dict = {}

    class FakeKMC:
        def run(self, input_path, output_path, working_directory, **kwargs):
            captured.update(
                input_path=input_path,
                output_path=output_path,
                working_directory=Path(working_directory),
                kwargs=kwargs,
            )
            assert captured["working_directory"].is_dir()
            Path(output_path).write_bytes(b"KFF\x01index-dataKFF")

    class FakeTransform:
        def dump(self, output_path):
            return self

        def run(self, input_path, **kwargs):
            return None

    monkeypatch.setattr(build_genome_kmer_index, "KMC", FakeKMC)
    monkeypatch.setattr(kff.KMCTools, "Transform", FakeTransform)
    dna = tmp_path / "dna.fa.gz"
    dna.write_bytes(b"input")
    output = tmp_path / "output" / "genome.kff"

    result = BuildGenomeKmerIndexStep().run_cli(
        [
            "--k",
            "16",
            "--dna",
            str(dna),
            "--n-threads",
            "6",
            "--kmer-index-output",
            str(output),
        ]
    )

    assert result == 0
    assert captured["input_path"] == dna
    assert captured["output_path"] == output
    assert captured["kwargs"] == {
        "k": 16,
        "m": 4,
        "f": "fm",
        "t": 6,
        "ci": 1,
        "o": "kff",
        "hp": True,
        "debug": False,
    }
    assert not captured["working_directory"].exists()
    assert output.is_file()


def test_config_rejects_k_above_kmc_limit(
    step: BuildGenomeKmerIndexStep,
    config: dict,
) -> None:
    config["parameters"]["target"]["k"] = 257

    with pytest.raises(ValueError, match=r"k must be between 1 and 256"):
        cfg.validate_step_config(config, [step], validate_input_files=False)
