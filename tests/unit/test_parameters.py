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
        ScalarParam("enabled", bool),
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
            "--enabled", "true",
            "--mode", "fast",
        ]
    )

    assert vars(args) == {
        "count": 5,
        "ratio": 0.5,
        "enabled": True,
        "optional_label": None,
        "source": "ensembl",
        "mode": "fast",
    }


@pytest.mark.parametrize(
    ("parameter", "value"),
    [
        (ScalarParam("enabled", bool), "yes"),
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


def test_scalar_parameter_rejects_path_annotations():
    with pytest.raises(TypeError, match="FileInput"):
        ScalarParam("input_file", Path)


def test_scalar_parameter_rejects_unsupported_cwl_annotations():
    with pytest.raises(TypeError, match="Unsupported CWL parameter annotation"):
        ScalarParam("values", list[str]).inferred_cwl_type()
