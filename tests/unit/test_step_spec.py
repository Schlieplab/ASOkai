#!/usr/bin/env python
"""
Filename: tests/unit/test_step_spec.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Version: 0.1.1
Description: Tests for the source-of-truth step specification.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

from typing import Literal

import pytest

from ASOkai._pipeline.contracts.files import FileInput, FileOutput
from ASOkai._pipeline.contracts.parameters import ScalarParam
from ASOkai._pipeline.contracts.step_spec import StepSpec
from ASOkai._pipeline.steps.base import Step


class _InputProducer(Step):
    name = "producer"
    description = "Test input producer."
    result_output = FileOutput("result", destination="result.json")
    spec = StepSpec(outputs=[result_output])


def _file_input(name: str = "input_file") -> FileInput:
    return FileInput(name, source=_InputProducer.result_output)


def test_step_spec_generates_declared_cwl_ports():
    spec = StepSpec(
        params=[ScalarParam("label", str)],
        inputs=[_file_input()],
        outputs=[FileOutput("result", destination="result.json")],
    )

    cwl_spec = spec.to_cwl_tool_spec()

    assert cwl_spec.input_types() == {
        "label": "string",
        "input_file": "File",
    }
    assert cwl_spec.output_names() == {"result"}


def test_step_spec_derives_config_maps():
    spec = StepSpec(
        params=[
            ScalarParam("configured", str, config="section.value"),
            ScalarParam("unconfigured", str),
            ScalarParam("internal", str, config="section.internal", cwl=False),
        ],
    )

    assert spec.config_map() == {"configured": "section.value"}


def test_step_spec_normalizes_declared_compatibility():
    spec = StepSpec(
        compatible_with={"antisense.mechanism": ["rnase-h1"]},
    )

    assert spec.compatible_with == {
        "antisense.mechanism": ("rnase-h1",),
    }


def test_step_spec_rejects_empty_compatibility_values():
    with pytest.raises(ValueError, match="must not be empty"):
        StepSpec(compatible_with={"analysis.mode": []})


def test_step_spec_builds_one_parser_from_all_parameter_kinds(tmp_path):
    parser = StepSpec(
        params=[
            ScalarParam("count", int),
            ScalarParam("source", str, default="ensembl"),
            ScalarParam("mode", Literal["fast", "careful"]),
        ],
        inputs=[_file_input()],
        outputs=[FileOutput("result", destination="result.json")],
    ).build_parser(description="Test parser.")

    args = parser.parse_args(
        [
            "--count", "5",
            "--input-file", str(tmp_path / "input.txt"),
            "--mode", "fast",
            "--result-output", str(tmp_path / "result.json"),
        ]
    )

    assert args.count == 5
    assert args.source == "ensembl"
    assert args.input_file == tmp_path / "input.txt"
    assert args.result_output == tmp_path / "result.json"


def test_step_spec_rejects_undeclared_output_path_inputs():
    with pytest.raises(ValueError, match="path references undeclared CWL input"):
        StepSpec(
            outputs=[FileOutput("result", destination="{missing}.json")],
        )


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"params": [ScalarParam("value", str), ScalarParam("value", int)]}, "parameter"),
        ({"inputs": [_file_input("file"), _file_input("file")]}, "input"),
        (
            {
                "outputs": [
                    FileOutput("result", destination="first.json"),
                    FileOutput("result", destination="second.json"),
                ],
            },
            "output",
        ),
        (
            {"params": [ScalarParam("shared", str)], "inputs": [_file_input("shared")]},
            "parameter/input",
        ),
    ],
)
def test_step_spec_rejects_duplicate_authored_names(kwargs, message):
    with pytest.raises(ValueError, match=rf"Duplicate {message} name"):
        StepSpec(**kwargs)


def test_step_spec_rejects_reserved_extra_keys():
    with pytest.raises(ValueError, match="cannot replace reserved keys: inputs"):
        StepSpec(extra={"inputs": {}})


def test_step_spec_derives_dependencies_and_supports_exact_lookups():
    source = _InputProducer.result_output
    spec = StepSpec(
        params=[ScalarParam("mode", str)],
        inputs=[
            FileInput("renamed_input", source=source),
            FileInput("second_input", source=source),
        ],
        outputs=[FileOutput("output", destination="output.txt")],
    )

    assert spec.dependencies() == ("producer",)
    assert spec.parameter("mode").name == "mode"
    assert spec.input("renamed_input").source is source
    assert spec.output("output").name == "output"
