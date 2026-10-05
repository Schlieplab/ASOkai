#!/usr/bin/env python
"""
Filename: tests/unit/test_build_kmc_index_step.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Tests for BuildKMCIndexStep.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from ASOkai._cwl.generation import StepCwlGenerator, generate_cwl_bundle
from ASOkai._pipeline import config as cfg
from ASOkai._pipeline.contracts.execution import StepInputBinding, StepRun
from ASOkai._pipeline.contracts.file_types import FastaFile, KffFile
from ASOkai._pipeline.plan import build_plan
from ASOkai._pipeline.steps.core.download_genome import DownloadGenomeStep
from ASOkai._pipeline.steps.utils.build_kmc_index import (
    BuildKMCIndexStep,
)
from ASOkai.Plugins import UtilityStep, Step


@pytest.fixture
def config(tmp_path: Path) -> dict:
    return {
        "datadir": str(tmp_path),
        "resources": {"build-kmc-index": {"n_threads": 6}},
        "parameters": {
            "genome": {
                "assembly": "GRCh38",
                "release": 114,
                "source": "ensembl",
                "species": "Homo_sapiens",
            },
            "target": {"k": 16},
        },
    }


@pytest.fixture
def step() -> BuildKMCIndexStep:
    return BuildKMCIndexStep()


def _run(step: BuildKMCIndexStep, config: dict, reference: Path) -> StepRun:
    return StepRun(
        step.name,
        step,
        config,
        inputs=(StepInputBinding(step.reference_input, reference),),
    )


def test_step_contract(step: BuildKMCIndexStep) -> None:
    assert isinstance(step, Step)
    assert isinstance(step, UtilityStep)
    assert step.name == "build-kmc-index"
    assert step.dependencies == []
    assert step.reference_input.source is None
    assert step.reference_input.file_type == FastaFile(gzip=None)
    assert isinstance(step.kmc_index_output.file_type, KffFile)
    assert step.config_map == {
        "k": "parameters.target.k",
        **{
            name: f"parameters.kmc.{name}"
            for name in (
                "m",
                "f",
                "sm",
                "hc",
                "p",
                "ci",
                "cs",
                "cx",
                "b",
                "r",
                "n",
                "sf",
                "sp",
                "sr",
                "opt_out_size",
            )
        },
    }
    assert step.supports_multiple_threads is True


def test_output_path_uses_configured_scope(
    step: BuildKMCIndexStep,
    config: dict,
    tmp_path: Path,
) -> None:
    output = _run(step, config, tmp_path / "dna.fa.gz").output_paths()["kmc_index"]

    assert output.parent == (
        tmp_path / "GRCh38" / "ensembl" / "114" / "indexes" / "kmc"
    )
    assert output.name == (
        "index.k16.m4.ffm.smFalse.hcFalse.pna.ci1.csna.cxna."
        "bFalse.rFalse.nna.sfna.spna.srna.opt_out_sizeFalse.kff"
    )


def test_output_name_changes_with_kmc_options(
    step: BuildKMCIndexStep,
    config: dict,
    tmp_path: Path,
) -> None:
    dna = tmp_path / "dna.fa.gz"
    original = _run(step, config, dna).output_paths()["kmc_index"]
    changed_option = StepRun(
        step.name,
        step,
        config,
        parameters={"ci": 2},
        inputs=(StepInputBinding(step.reference_input, dna),),
    ).output_paths()["kmc_index"]
    assert original != changed_option
    assert ".ci2." in changed_option.name
    assert original == _run(step, config, dna).output_paths()["kmc_index"]


@pytest.mark.parametrize(
    ("missing_field", "config_path"),
    [
        ("assembly", "parameters.genome.assembly"),
        ("source", "parameters.genome.source"),
        ("release", "parameters.genome.release"),
    ],
)
def test_planning_rejects_missing_genome_identity(
    step: BuildKMCIndexStep,
    tmp_path: Path,
    missing_field: str,
    config_path: str,
) -> None:
    reference = tmp_path / "dna.fa"
    reference.write_text(">chr1\nACGTACGT\n", encoding="utf-8")
    config = {
        "datadir": str(tmp_path),
        "parameters": {
            "genome": {
                "assembly": "GRCh38",
                "source": "ensembl",
                "release": 114,
            }
        },
        "runs": [
            {
                "step": "build-kmc-index",
                "parameters": {"k": 4},
                "inputs": {"reference": {"path": str(reference)}},
            }
        ],
    }
    del config["parameters"]["genome"][missing_field]

    with pytest.raises(ValueError, match=config_path):
        build_plan([], config, _registry={step.name: step})


def test_named_download_links_directly_to_kmc_builder(
    step: BuildKMCIndexStep,
    tmp_path: Path,
) -> None:
    downloader = DownloadGenomeStep()
    config = {
        "datadir": str(tmp_path),
        "parameters": {
            "genome": {
                "assembly": "GRCh38",
                "source": "ensembl",
                "release": 114,
                "species": "Homo_sapiens",
            }
        },
        "runs": [
            {"step": "download-genome", "id": "genome"},
            {
                "step": "build-kmc-index",
                "id": "index",
                "parameters": {"k": 16},
                "inputs": {"reference": {"from": "run.genome.dna"}},
            },
        ],
    }

    plan = build_plan(
        [], config, _registry={downloader.name: downloader, step.name: step}
    )
    assert [run.step.name for run in plan.runs_to_execute] == [
        "download-genome",
        "build-kmc-index",
    ]
    genome, index = plan.runs_to_execute
    assert index.input_paths()["reference"] == genome.output_paths()["dna"]


def test_cwl_spec_exposes_runtime_resources(
    step: BuildKMCIndexStep,
    config: dict,
    tmp_path: Path,
) -> None:
    doc = yaml.safe_load(
        StepCwlGenerator().render(_run(step, config, tmp_path / "dna.fa.gz"))
    )

    assert set(doc["inputs"]) == {
        *step.config_map,
        "reference",
        "n_threads",
    }
    assert doc["inputs"]["n_threads"]["inputBinding"] == {"prefix": "--n-threads"}
    filename = (
        _run(step, config, tmp_path / "dna.fa.gz").output_paths()["kmc_index"].name
    )
    assert {
        "prefix": "--kmc-index-output",
        "valueFrom": filename,
    } in doc["arguments"]


def test_generated_workflow_passes_configured_resources(
    step: BuildKMCIndexStep,
    config: dict,
    tmp_path: Path,
) -> None:
    generated = generate_cwl_bundle([_run(step, config, tmp_path / "dna.fa.gz")])
    workflow = yaml.safe_load(generated.run_cwl)
    tool = yaml.safe_load(generated.step_cwls["build-kmc-index.cwl"])

    step_inputs = workflow["steps"]["step_build_kmc_index"]["in"]
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
    from ASOkai._pipeline.steps.utils import build_kmc_index

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

    monkeypatch.setattr(build_kmc_index, "KMC", FakeKMC)
    monkeypatch.setattr(kff.KMCTools, "Transform", FakeTransform)
    dna = tmp_path / "dna.fa.gz"
    dna.write_bytes(b"input")
    output = tmp_path / "output" / "genome.kff"

    result = BuildKMCIndexStep().run_cli(
        [
            "--k",
            "16",
            "--reference",
            str(dna),
            "--n-threads",
            "6",
            "--kmc-index-output",
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
        "sm": False,
        "hc": False,
        "p": None,
        "ci": 1,
        "cs": None,
        "cx": None,
        "b": False,
        "r": False,
        "n": None,
        "sf": None,
        "sp": None,
        "sr": None,
        "opt_out_size": False,
        "o": "kff",
        "hp": True,
        "debug": False,
    }
    assert not captured["working_directory"].exists()
    assert output.is_file()


def test_run_cli_forwards_selected_kmc_options(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from ASOkai._pipeline.contracts.file_types import kff
    from ASOkai._pipeline.steps.utils import build_kmc_index

    captured: dict = {}

    class FakeKMC:
        def run(self, input_path, output_path, working_directory, **kwargs):
            captured.update(kwargs)
            Path(output_path).write_bytes(b"KFF\x01index-dataKFF")

    class FakeTransform:
        def dump(self, output_path):
            return self

        def run(self, input_path, **kwargs):
            return None

    monkeypatch.setattr(build_kmc_index, "KMC", FakeKMC)
    monkeypatch.setattr(kff.KMCTools, "Transform", FakeTransform)
    dna = tmp_path / "dna.fa.gz"
    dna.write_bytes(b"input")
    output = tmp_path / "index.kff"

    result = BuildKMCIndexStep().run_cli(
        [
            "--k",
            "16",
            "--m",
            "8",
            "--f",
            "fa",
            "--hc",
            "--p",
            "9",
            "--ci",
            "2",
            "--cs",
            "100",
            "--cx",
            "500",
            "--b",
            "--n",
            "32",
            "--sf",
            "2",
            "--sp",
            "3",
            "--sr",
            "4",
            "--opt-out-size",
            "--reference",
            str(dna),
            "--kmc-index-output",
            str(output),
        ]
    )

    assert result == 0
    assert {
        name: captured[name]
        for name in (
            "m",
            "f",
            "hc",
            "p",
            "ci",
            "cs",
            "cx",
            "b",
            "n",
            "sf",
            "sp",
            "sr",
            "opt_out_size",
        )
    } == {
        "m": 8,
        "f": "fa",
        "hc": True,
        "p": 9,
        "ci": 2,
        "cs": 100,
        "cx": 500,
        "b": True,
        "n": 32,
        "sf": 2,
        "sp": 3,
        "sr": 4,
        "opt_out_size": True,
    }


def test_config_rejects_k_above_kmc_limit(
    step: BuildKMCIndexStep,
    config: dict,
) -> None:
    config["parameters"]["target"]["k"] = 257

    with pytest.raises(ValueError, match=r"k must be between 1 and 256"):
        cfg.validate_step_config(config, [step], validate_input_files=False)


@pytest.mark.parametrize(
    ("options", "message"),
    [
        ({"m": 1}, "m must be between 2 and 1024"),
        ({"p": 11}, "p must be between 5 and 11 and no greater than k"),
        ({"ci": 3, "cx": 2}, "ci must be no greater than cx"),
        ({"n": 0}, "n must be a positive integer"),
    ],
)
def test_config_rejects_invalid_kmc_options(step, config, options, message):
    if "p" in options:
        config["parameters"]["target"]["k"] = 8
    config["parameters"]["kmc"] = options

    with pytest.raises(ValueError, match=message):
        cfg.validate_step_config(config, [step], validate_input_files=False)
