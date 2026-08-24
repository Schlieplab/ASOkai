#!/usr/bin/env python
"""
Filename: tests/unit/test_cwl_step_spec.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Version: 0.1.1
Description: Tests for systematic step parameter specs.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path
from typing import Any, Literal, cast

import pytest

from ASOkai.Utils import Serializable
from ASOkai._pipeline.contracts.file_types import JsonFile
from ASOkai._pipeline.contracts.files import FileInput, FileOutput
from ASOkai._pipeline.contracts.parameters import (
    Param,
    ScalarParam,
)
from ASOkai._pipeline.contracts.paths import (
    OutputPathTemplate,
    TemplateField,
)
from ASOkai._pipeline.contracts.step_spec import StepSpec
from ASOkai._pipeline.steps.base import Step


class _InputProducer(Step):
    name = "producer"
    description = "Test input producer."
    result_output = FileOutput("result", destination="result.json")
    spec = StepSpec(outputs=[result_output])


class _ConfigurableInputProducer(Step):
    name = "configurable-producer"
    description = "Test producer with a configurable output."
    result_output = FileOutput("result", destination="{region}/result.json")
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


def _file_input(name: str = "input_file") -> FileInput:
    return FileInput(name, source=_InputProducer.result_output)


def test_parameter_types_share_the_param_base_contract():
    assert issubclass(ScalarParam, Param)
    assert issubclass(FileInput, Param)
    assert issubclass(FileOutput, Param)
    assert inspect.isabstract(Param)


def test_file_input_references_the_producers_exact_output_declaration():
    file_input = _file_input()

    assert file_input.source is _InputProducer.result_output
    assert file_input.source.producer == "producer"


def test_file_input_uses_standard_consumer_configuration_paths(tmp_path):
    file_input = FileInput(
        "target",
        source=_ConfigurableInputProducer.result_output,
        configurable_parameters=("region",),
    )
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
            source=_ConfigurableInputProducer.result_output,
            configurable_parameters=("missing",),
        )


def test_file_input_rejects_path_and_parameters_together():
    file_input = FileInput(
        "target",
        source=_ConfigurableInputProducer.result_output,
        configurable_parameters=("region",),
    )
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
        file_input.configured_path_override(config, "consumer")


def test_file_input_rejects_unexposed_configured_parameters():
    file_input = FileInput(
        "target",
        source=_ConfigurableInputProducer.result_output,
        configurable_parameters=("region",),
    )
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
        file_input.configured_parameters(config, "consumer")


def test_step_output_must_be_declared_as_a_class_attribute():
    with pytest.raises(TypeError, match="must be declared once as a class attribute"):

        class InlineOutputStep(Step):
            name = "inline-output"
            description = "Invalid test step."
            spec = StepSpec(
                outputs=[FileOutput("result", destination="result.json")]
            )


def test_typed_json_file_uses_serializable_annotations():
    class Data(Serializable):
        count: int

        def __init__(self, count):
            self.count = count
            super().__init__()

    output = FileOutput(
        "result",
        file_type=JsonFile(Data),
        destination="result.json",
    )

    assert json.loads(output.dumps(Data(1)))["count"] == 1
    with pytest.raises(ValueError, match=r"\$.count"):
        output.dumps(Data("not-an-integer"))
    with pytest.raises(TypeError, match="requires Data"):
        output.dumps(cast(Any, "not-a-Data"))


def test_step_spec_infers_cwl_types_from_annotations():
    spec = StepSpec(
        params=[
            ScalarParam("label", str),
            ScalarParam("count", int),
            ScalarParam("optional_label", str | None),
            ScalarParam("mode", Literal["fast", "careful"]),
        ],
        inputs=[_file_input()],
        outputs=[
            FileOutput("result", destination="result.json"),
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
            FileInput(
                "file_input",
                source=_InputProducer.result_output,
            ),
        ],
    )

    cwl_spec = spec.to_cwl_tool_spec()

    assert spec.config_map() == {"scalar": "section.scalar"}
    assert cwl_spec.input_names() == {"scalar", "file_input"}
    assert cwl_spec.input_types()["file_input"] == "File"


def test_step_spec_uses_only_declared_compatibility():
    spec = StepSpec(
        params=[
            ScalarParam(
                "mode",
                Literal["fast", "careful"],
                config="analysis.mode",
            ),
        ],
        compatible_with={
            "antisense.mechanism": ["rnase-h1"],
        },
    )

    assert spec.compatible_with == {
        "antisense.mechanism": ("rnase-h1",),
    }


def test_step_spec_rejects_empty_compatibility_values():
    with pytest.raises(ValueError, match="must not be empty"):
        StepSpec(compatible_with={"analysis.mode": []})


def test_step_spec_builds_argparse_parser_from_params(tmp_path):
    parser = StepSpec(
        params=[
            ScalarParam("count", int),
            ScalarParam("optional_label", str | None),
            ScalarParam("source", str, default="ensembl"),
            ScalarParam("mode", Literal["fast", "careful"]),
        ],
        inputs=[_file_input()],
        outputs=[
            FileOutput("result", destination="result.json"),
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
    with pytest.raises(TypeError, match="FileInput"):
        ScalarParam("input_file", Path)


def test_file_output_generates_fixed_argument_and_static_output_glob():
    spec = StepSpec(
        outputs=[
            FileOutput(
                "result",
                destination="result.json",
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
                FileOutput(
                    "result",
                    destination="{missing}.json",
                )
            ],
        )


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"params": [ScalarParam("value", str), ScalarParam("value", int)]}, "parameter"),
        ({"inputs": [_file_input("file"), _file_input("file")]}, "input"),
        (
            {
                "outputs": [
                    FileOutput("result", destination="result.json"),
                    FileOutput("result", destination="result.json"),
                ]
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


def test_step_spec_rejects_unsupported_cwl_annotations():
    spec = StepSpec(params=[ScalarParam("ratio", float)])

    with pytest.raises(TypeError, match="Unsupported CWL parameter annotation"):
        spec.to_cwl_tool_spec()


def test_step_spec_validates_runtime_output_names(tmp_path):
    spec = StepSpec(
        outputs=[FileOutput("result", destination="result.json")]
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


def test_file_output_derives_working_filename_from_rendered_destination():
    output = FileOutput(
        "result",
        destination="{sample}/named-{sample}.json",
    )

    assert output.working_filename({"sample": "A"}) == "named-A.json"
    assert "temp_filename" not in inspect.signature(FileOutput).parameters


def test_output_path_template_rejects_paths_outside_datadir():
    destination = OutputPathTemplate("../{sample}.json")

    with pytest.raises(ValueError, match="stay below datadir"):
        destination.render({"sample": "result"})


def test_step_spec_derives_dependencies_and_supports_exact_lookups():
    source = _InputProducer.result_output
    spec = StepSpec(
        inputs=[
            FileInput("renamed_input", source=source),
            FileInput("second_input", source=source),
        ],
        outputs=[FileOutput("output", destination="output.txt")],
    )

    assert spec.dependencies() == ("producer",)
    assert spec.input("renamed_input").source == source
    assert spec.output("output").name == "output"
