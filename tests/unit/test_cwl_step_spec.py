#!/usr/bin/env python
"""Tests for systematic step parameter specs."""
from __future__ import annotations

import inspect
from pathlib import Path
from typing import Literal

import pytest

from ASOkai._cwl.spec import (
    TemplateField,
    OutputPathTemplate,
    InputParam,
    OutputParam,
    Param,
    ScalarParam,
    StepSpec,
)


def test_parameter_types_share_the_param_base_contract():
    assert issubclass(ScalarParam, Param)
    assert issubclass(InputParam, Param)
    assert issubclass(OutputParam, Param)
    assert inspect.isabstract(Param)


def test_step_spec_infers_cwl_types_from_annotations():
    spec = StepSpec(
        params=[
            ScalarParam("label", str),
            ScalarParam("count", int),
            ScalarParam("optional_label", str | None),
            ScalarParam("mode", Literal["fast", "careful"]),
        ],
        inputs=[InputParam("input_file")],
        outputs=[
            OutputParam("result", temp_filename="result.json"),
        ],
    )

    cwl_spec = spec.to_cwl_tool_spec()

    assert cwl_spec.input_types()["label"] == "string"
    assert cwl_spec.input_types()["count"] == "int"
    assert cwl_spec.input_types()["input_file"] == "File"
    assert cwl_spec.input_types()["optional_label"] == "string?"
    assert cwl_spec.input_types()["mode"] == {
        "type": "enum",
        "symbols": ["fast", "careful"],
    }
    assert cwl_spec.output_names() == {"result"}


def test_step_spec_infers_optional_literal_as_nullable_enum():
    spec = StepSpec(
        params=[ScalarParam("mode", Literal["fast", "careful"] | None)],
    )

    assert spec.to_cwl_tool_spec().input_types()["mode"] == [
        "null",
        {"type": "enum", "symbols": ["fast", "careful"]},
    ]


def test_step_spec_derives_config_maps_and_cwl_inputs():
    spec = StepSpec(
        params=[
            ScalarParam("scalar", str, config="section.scalar"),
        ],
        inputs=[
            InputParam("file_input", override="section.file"),
            InputParam("parser_only", cwl=False),
        ],
    )

    cwl_spec = spec.to_cwl_tool_spec()

    assert spec.config_map() == {"scalar": "section.scalar"}
    assert spec.input_overrides() == {"file_input": "section.file"}
    assert cwl_spec.input_names() == {"scalar", "file_input"}
    assert cwl_spec.input_types()["file_input"] == "File"


def test_step_spec_builds_argparse_parser_from_params(tmp_path):
    parser = StepSpec(
        params=[
            ScalarParam("count", int),
            ScalarParam("optional_label", str | None),
            ScalarParam("source", str, default="ensembl"),
            ScalarParam("mode", Literal["fast", "careful"]),
        ],
        inputs=[InputParam("input_file")],
        outputs=[
            OutputParam("result", temp_filename="result.json"),
        ],
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
    assert args.input_file == tmp_path / "input.txt"
    assert args.optional_label is None
    assert args.source == "ensembl"
    assert args.mode == "fast"
    assert args.result_output == tmp_path / "result.json"
    assert not hasattr(args, "output")


def test_scalar_param_rejects_path_annotations():
    with pytest.raises(TypeError, match="InputParam"):
        ScalarParam("input_file", Path)


def test_output_param_generates_fixed_argument_and_static_output_glob():
    spec = StepSpec(
        outputs=[
            OutputParam(
                "result",
                temp_filename="result.json",
                doc="Result JSON.",
            ),
        ],
    )

    cwl_spec = spec.to_cwl_tool_spec()

    assert cwl_spec.input_names() == set()
    assert cwl_spec.arguments[-1].prefix == "--result-output"
    assert cwl_spec.arguments[-1].value_from == "result.json"
    assert cwl_spec.outputs[0].name == "result"
    assert cwl_spec.outputs[0].glob == "result.json"
    assert "InlineJavascriptRequirement" not in cwl_spec.requirements


def test_step_spec_parser_uses_literal_choices(tmp_path):
    parser = StepSpec(
        params=[
            ScalarParam("mode", Literal["fast", "careful"]),
        ],
    ).build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["--mode", "wrong"])


def test_step_spec_rejects_undeclared_output_path_inputs():
    with pytest.raises(ValueError, match="path references undeclared CWL input"):
        StepSpec(
            outputs=[
                OutputParam(
                    "result",
                    temp_filename="result.json",
                    destination="{missing}.json",
                )
            ],
        )


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"params": [ScalarParam("value", str), ScalarParam("value", int)]}, "parameter"),
        ({"inputs": [InputParam("file"), InputParam("file")]}, "input"),
        (
            {
                "outputs": [
                    OutputParam("result", temp_filename="result.json"),
                    OutputParam("result", temp_filename="result.json"),
                ]
            },
            "output",
        ),
        (
            {"params": [ScalarParam("shared", str)], "inputs": [InputParam("shared")]},
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


def test_step_spec_rejects_unsupported_cwl_annotations():
    spec = StepSpec(params=[ScalarParam("ratio", float)])

    with pytest.raises(TypeError, match="Unsupported CWL parameter annotation"):
        spec.to_cwl_tool_spec()


def test_step_spec_validates_runtime_output_names(tmp_path):
    spec = StepSpec(
        outputs=[OutputParam("result", temp_filename="result.json")]
    )

    spec.validate_output_paths({"result": tmp_path / "result.json"})

    with pytest.raises(ValueError, match="missing: result"):
        spec.validate_output_paths({"other": tmp_path / "other.json"})


def test_output_path_template_renders_structured_fallback_and_transform():
    destination = OutputPathTemplate(
        "{species}.{target}.json",
        fields={
            "species": TemplateField("species", transform="species_case"),
            "target": TemplateField.first_of("target_id", "target_name"),
        },
    )

    assert destination.render(
        {
            "species": "homo_SAPIENS",
            "target_id": None,
            "target_name": "KRAS",
        }
    ).as_posix() == "Homo_sapiens.KRAS.json"
    assert destination.input_names() == {"species", "target_id", "target_name"}


def test_output_path_template_rejects_unknown_field_rules():
    with pytest.raises(ValueError, match="not used by the template"):
        OutputPathTemplate("result.json", fields={"unused": TemplateField("value")})


def test_output_param_rejects_dynamic_cwl_temp_filenames():
    with pytest.raises(ValueError, match="stable temporary filename"):
        OutputParam("result", temp_filename="{sample}.json")


def test_output_param_requires_named_temp_filename():
    parameter = inspect.signature(OutputParam).parameters["temp_filename"]

    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY


def test_output_path_template_rejects_paths_outside_datadir():
    destination = OutputPathTemplate("../{sample}.json")

    with pytest.raises(ValueError, match="stay below datadir"):
        destination.render({"sample": "result"})
