#!/usr/bin/env python
"""Tests for scalar step-parameter contracts."""

import argparse
from pathlib import Path
from typing import Literal

import pytest

from ASOkai._pipeline.contracts.parameters import ScalarParam


@pytest.mark.parametrize(
    ("annotation", "expected"),
    [
        (str, "string"),
        (int, "int"),
        (float, "double"),
        (bool, "boolean"),
        (str | None, "string?"),
        (
            Literal["fast", "careful"],
            {"type": "enum", "symbols": ["fast", "careful"]},
        ),
        (
            Literal["fast", "careful"] | None,
            [
                "null",
                {"type": "enum", "symbols": ["fast", "careful"]},
            ],
        ),
    ],
)
def test_scalar_parameter_infers_cwl_type(annotation, expected):
    assert ScalarParam("value", annotation).inferred_cwl_type() == expected


def test_scalar_parameters_build_their_parser_options():
    parser = argparse.ArgumentParser()
    parameters = [
        ScalarParam("count", int),
        ScalarParam("ratio", float),
        ScalarParam("optional_label", str | None),
        ScalarParam("source", str, default="ensembl"),
        ScalarParam("mode", Literal["fast", "careful"]),
    ]
    for parameter in parameters:
        parameter.add_to_parser(parser)

    args = parser.parse_args(
        [
            "--count", "5",
            "--ratio", "0.5",
            "--mode", "fast",
        ]
    )

    assert vars(args) == {
        "count": 5,
        "ratio": 0.5,
        "optional_label": None,
        "source": "ensembl",
        "mode": "fast",
    }


@pytest.mark.parametrize(
    ("parameter", "value"),
    [
        (ScalarParam("mode", Literal["fast", "careful"]), "wrong"),
    ],
)
def test_scalar_parameter_parser_rejects_invalid_values(parameter, value):
    parser = argparse.ArgumentParser()
    parameter.add_to_parser(parser)

    with pytest.raises(SystemExit):
        parser.parse_args([parameter.cli_prefix, value])


def test_scalar_parameter_validation_does_not_treat_bool_as_int():
    with pytest.raises(ValueError, match="must be int"):
        ScalarParam("count", int).validate(True)


def test_boolean_parameter_is_a_presence_flag():
    parser = argparse.ArgumentParser()
    parameter = ScalarParam("enabled", bool)
    parameter.add_to_parser(parser)

    assert parser.parse_args([]).enabled is False
    assert parser.parse_args(["--enabled"]).enabled is True
    assert parameter.to_cwl_input().to_cwl() == {
        "type": "boolean",
        "default": False,
        "inputBinding": {"prefix": "--enabled"},
    }


@pytest.mark.parametrize(
    ("annotation", "value"),
    [
        (str, 1),
        (int, True),
        (float, 1),
        (bool, "true"),
        (Literal["fast", "careful"], "wrong"),
    ],
)
def test_scalar_parameter_rejects_invalid_defaults(annotation, value):
    with pytest.raises(ValueError):
        ScalarParam("value", annotation, default=value)


def test_optional_scalar_parameter_accepts_a_null_default():
    parameter = ScalarParam("label", str | None, default=None)

    assert parameter.parser_required() is False
    parameter.validate(None)


def test_scalar_parameter_rejects_path_annotations():
    with pytest.raises(TypeError, match="FileInput"):
        ScalarParam("input_file", Path)


@pytest.mark.parametrize("annotation", [bool | None, list[str]])
def test_scalar_parameter_rejects_unsupported_annotations_during_construction(
    annotation,
):
    with pytest.raises(TypeError):
        ScalarParam("value", annotation)


def test_boolean_flag_rejects_a_true_default():
    with pytest.raises(ValueError, match="must default to false"):
        ScalarParam("enabled", bool, default=True)


def test_scalar_parameter_rejects_non_string_literal_values():
    with pytest.raises(TypeError, match="Literal values must all be strings"):
        ScalarParam("level", Literal[1, 2])


@pytest.mark.parametrize("config", ["", "section..value"])
def test_scalar_parameter_rejects_invalid_config_paths(config):
    with pytest.raises(ValueError, match="non-blank dotted path"):
        ScalarParam("value", str, config=config)
