#!/usr/bin/env python
"""Tests for structured pipeline output-path templates."""

from typing import Any, cast

import pytest

from ASOkai._pipeline.contracts.paths import (
    InputConfigField,
    OutputPathTemplate,
    TemplateField,
)


def test_output_path_renders_fallbacks():
    destination = OutputPathTemplate(
        "{species}.{target}.json",
        fields={
            "species": TemplateField("genome.species"),
            "target": TemplateField.first_of(
                "target.target_id",
                "target.target_name",
            ),
        },
    )

    assert destination.render(
        {
            "genome": {"species": "Homo_sapiens"},
            "target": {
                "target_id": None,
                "target_name": "KRAS",
            },
        }
    ).as_posix() == "Homo_sapiens.KRAS.json"
    assert destination.config_paths() == {
        "genome.species",
        "target.target_id",
        "target.target_name",
    }


def test_output_path_rejects_unused_field_rules():
    with pytest.raises(ValueError, match="not used by the template"):
        OutputPathTemplate(
            "result.json",
            fields={"unused": TemplateField("value")},
        )


@pytest.mark.parametrize(
    "config_path",
    ["", "genome..species"],
)
def test_template_field_rejects_invalid_config_paths(config_path):
    with pytest.raises(ValueError, match="non-blank dotted paths"):
        TemplateField(config_path)


def test_template_field_first_of_requires_a_config_path():
    with pytest.raises(ValueError, match="requires at least one"):
        TemplateField.first_of()


def test_input_config_field_requires_a_named_input():
    with pytest.raises(ValueError, match="input_name must be non-blank"):
        InputConfigField("", "target.region")


@pytest.mark.parametrize(
    "template",
    ["{sample.name}", "{sample!r}"],
)
def test_output_path_rejects_complex_format_fields(template):
    with pytest.raises(ValueError, match="simple input name|format specs"):
        OutputPathTemplate(template)


def test_output_path_rejects_invalid_field_declarations():
    with pytest.raises(TypeError, match="must be TemplateField"):
        OutputPathTemplate(
            "{sample}.json",
            fields={"sample": cast(Any, "section.sample")},
        )


def test_output_path_can_read_each_file_inputs_configuration():
    destination = OutputPathTemplate(
        "{sites}_against_{target}.csv",
        fields={
            "sites": InputConfigField("sites", "target.region"),
            "target": InputConfigField("target", "target.region"),
        },
    )

    path = destination.render(
        {},
        {
            "sites": {"target": {"region": "pre-mrna"}},
            "target": {"target": {"region": "transcriptomic"}},
        },
    )

    assert path.as_posix() == (
        "pre-mrna_against_transcriptomic.csv"
    )
    assert destination.config_paths() == {"target.region"}
    assert destination.input_names() == {"sites", "target"}


def test_output_path_requires_every_referenced_file_input():
    destination = OutputPathTemplate(
        "{target}.csv",
        fields={"target": InputConfigField("target", "target.region")},
    )

    with pytest.raises(
        ValueError,
        match="resolved configuration.*'target'",
    ):
        destination.render({})


def test_input_config_field_static_validation_uses_main_configuration():
    destination = OutputPathTemplate(
        "{mode}.csv",
        fields={"mode": InputConfigField("sites", "producer.mode")},
    )

    destination.validate_configuration({"producer": {"mode": "main"}})

    with pytest.raises(ValueError, match="No value is available"):
        destination.validate_configuration({})


def test_output_path_requires_a_value_for_each_field():
    with pytest.raises(ValueError, match="No value is available"):
        OutputPathTemplate("{sample}.json").render({})


def test_output_path_requires_scalar_field_values():
    with pytest.raises(TypeError, match="must be scalar"):
        OutputPathTemplate("{sample}.json").render({"sample": ["one"]})


@pytest.mark.parametrize(
    "template",
    [
        "../result.json",
        "/result.json",
        "C:/outside/result.json",
        r"C:\outside\result.json",
    ],
)
def test_output_path_must_stay_below_datadir(template):
    with pytest.raises(ValueError, match="stay below datadir"):
        OutputPathTemplate(template).render({})


def test_output_path_rejects_traversal_from_a_resolved_value():
    with pytest.raises(ValueError, match="stay below datadir"):
        OutputPathTemplate("{sample}/result.json").render(
            {"sample": "../outside"}
        )
