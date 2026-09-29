#!/usr/bin/env python
"""
Filename: tests/unit/test_file_contracts.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Tests for pipeline file input and output declarations.
License: LGPL-3.0-or-later
"""

from typing import Literal

import pytest

from ASOkai._pipeline.contracts.files import FileInput, FileOutput
from ASOkai._pipeline.contracts.file_types import FastaFile
from ASOkai._pipeline.contracts.parameters import ScalarParam
from ASOkai._pipeline.contracts.paths import OutputPathTemplate, TemplateField
from ASOkai._pipeline.contracts.step_spec import StepSpec
from ASOkai._pipeline.steps.base import Step


class ProducerStep(Step):
    name = "producer"
    description = "Test input producer."
    result_output = FileOutput("result", destination="result.json")
    spec = StepSpec(outputs=[result_output])


class ConfigurableProducerStep(Step):
    name = "configurable-producer"
    description = "Test producer with a configurable output."
    result_output = FileOutput(
        "result",
        destination=OutputPathTemplate(
            "{region}/result.json",
            fields={"region": TemplateField("target.region")},
        ),
    )
    spec = StepSpec(
        params=[
            ScalarParam(
                "region",
                Literal["exonic", "transcriptomic"],
                config="target.region",
            ),
        ],
        outputs=[result_output],
    )


def _configurable_input() -> FileInput:
    return FileInput(
        "target",
        source=ConfigurableProducerStep.result_output,
        configurable_parameters=("region",),
    )


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


def test_file_input_reads_path_or_parameter_configuration(tmp_path):
    file_input = _configurable_input()
    path_override = tmp_path / "target.json"

    assert file_input.configuration_path("consumer") == (
        "steps.consumer.inputs.target"
    )
    assert file_input.configured_path_override(
        {
            "steps": {
                "consumer": {
                    "inputs": {
                        "target": {"path_override": str(path_override)},
                    },
                },
            },
        },
        "consumer",
    ) == path_override.resolve()
    assert file_input.configured_parameters(
        {
            "steps": {
                "consumer": {
                    "inputs": {
                        "target": {
                            "parameters": {"region": "transcriptomic"},
                        },
                    },
                },
            },
        },
        "consumer",
    ) == {"region": "transcriptomic"}


def test_file_input_rejects_unknown_configurable_producer_parameter():
    with pytest.raises(ValueError, match="unknown parameter 'missing'"):
        FileInput(
            "target",
            source=ConfigurableProducerStep.result_output,
            configurable_parameters=("missing",),
        )


def test_file_input_rejects_path_and_parameters_together():
    config = {
        "steps": {
            "consumer": {
                "inputs": {
                    "target": {
                        "path_override": "target.json",
                        "parameters": {"region": "transcriptomic"},
                    },
                },
            },
        },
    }

    with pytest.raises(ValueError, match="exactly one"):
        _configurable_input().configured_path_override(config, "consumer")


def test_file_input_rejects_unexposed_configured_parameters():
    config = {
        "steps": {
            "consumer": {
                "inputs": {
                    "target": {"parameters": {"missing": "value"}},
                },
            },
        },
    }

    with pytest.raises(ValueError, match="does not allow parameter.*missing"):
        _configurable_input().configured_parameters(config, "consumer")


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
