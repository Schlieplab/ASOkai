#!/usr/bin/env python
"""
Filename: tests/unit/test_file_contracts.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Tests for pipeline file input and output declarations.
License: LGPL-3.0-or-later
"""

import pytest

from ASOkai._pipeline.contracts.files import FileInput, FileOutput
from ASOkai._pipeline.contracts.file_types import FastaFile
from ASOkai._pipeline.contracts.run_spec import FromRun
from ASOkai._pipeline.contracts.step_spec import StepSpec
from ASOkai._pipeline.steps.base import Step


class ProducerStep(Step):
    name = "producer"
    description = "Test input producer."
    result_output = FileOutput("result", destination="result.json")
    spec = StepSpec(outputs=[result_output])


def test_file_input_inherits_its_exact_producer_output():
    file_input = FileInput("result", source=ProducerStep.result_output)

    assert file_input.source is ProducerStep.result_output
    assert file_input.source.producer == "producer"
    assert file_input.file_type is ProducerStep.result_output.file_type


def test_typed_file_input_accepts_matching_fasta_format_only():
    file_input = FileInput("reference", file_type=FastaFile(gzip=False))
    plain = FileOutput(
        "plain", destination="plain.fa", file_type=FastaFile(gzip=False)
    )
    compressed = FileOutput(
        "compressed", destination="compressed.fa.gz", file_type=FastaFile(gzip=True)
    )

    assert file_input.source is None
    assert file_input.accepts_output(plain)
    assert not file_input.accepts_output(compressed)

    either = FileInput("reference", file_type=FastaFile(gzip=None))
    assert either.accepts_output(plain)
    assert either.accepts_output(compressed)


def test_file_input_requires_one_source_contract():
    with pytest.raises(ValueError, match="exactly one of source or file_type"):
        FileInput("reference")
    with pytest.raises(ValueError, match="exactly one of source or file_type"):
        FileInput(
            "reference",
            source=ProducerStep.result_output,
            file_type=FastaFile(),
        )


def test_file_output_cannot_be_shared_by_two_producer_steps():
    output = FileOutput("result", destination="result.json")

    class FirstProducerStep(Step):
        name = "first-producer"
        description = "First test producer."
        result_output = output
        spec = StepSpec(outputs=[result_output])

    with pytest.raises(ValueError, match="already owned by 'first-producer'"):

        class SecondProducerStep(Step):
            name = "second-producer"
            description = "Second test producer."
            result_output = output
            spec = StepSpec(outputs=[result_output])


def test_file_input_reads_path(tmp_path):
    file_input = FileInput("target", source=ProducerStep.result_output)
    path = tmp_path / "target.json"

    assert file_input.configuration_path("consumer") == (
        "steps.consumer.inputs.target"
    )
    assert file_input.configured_source(
        {
            "steps": {
                "consumer": {
                    "inputs": {
                        "target": {"path": str(path)},
                    },
                },
            },
        },
        "consumer",
    ) == path.resolve()


def test_file_input_rejects_removed_parameter_configuration():
    config = {
        "steps": {
            "consumer": {
                "inputs": {
                    "target": {"parameters": {"region": "exonic"}},
                },
            },
        },
    }

    file_input = FileInput("target", source=ProducerStep.result_output)
    with pytest.raises(ValueError, match="only path or from"):
        file_input.configured_source(config, "consumer")


def test_file_input_reads_named_source_without_fixed_producer():
    file_input = FileInput("reference", file_type=FastaFile())
    configured = file_input.configured_source(
        {
            "steps": {
                "consumer": {
                    "inputs": {"reference": {"from": "run.reference.fasta"}},
                },
            },
        },
        "consumer",
    )
    assert configured == FromRun("reference", "fasta")


def test_file_output_generates_its_cli_argument_and_cwl_output():
    output = FileOutput(
        "result",
        destination="results/{sample}/named-{sample}.json",
        doc="Result JSON.",
    )

    argument = output.to_cwl_argument({"sample": "A"})
    cwl_output = output.to_cwl_output({"sample": "A"})

    assert argument.prefix == "--result-output"
    assert argument.value_from == "named-A.json"
    assert cwl_output.name == "result"
    assert cwl_output.glob == "named-A.json"
