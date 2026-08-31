#!/usr/bin/env python
"""Tests for structured pipeline output-path templates."""

import pytest

from ASOkai._pipeline.contracts.paths import (
    InputConfigField,
    OutputPathTemplate,
    TemplateField,
)


def test_output_path_renders_fallbacks_and_transforms():
    destination = OutputPathTemplate(
        "{species}.{target}.json",
        fields={
            "species": TemplateField(
                "genome.species",
                transform="species_case",
            ),
            "target": TemplateField.first_of(
                "target.target_id",
                "target.target_name",
            ),
        },
    )

    assert destination.render(
        {
            "genome": {"species": "homo_SAPIENS"},
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


def test_output_path_requires_a_value_for_each_field():
    with pytest.raises(ValueError, match="No value is available"):
        OutputPathTemplate("{sample}.json").render({})


@pytest.mark.parametrize("template", ["../result.json", "/result.json"])
def test_output_path_must_stay_below_datadir(template):
    with pytest.raises(ValueError, match="stay below datadir"):
        OutputPathTemplate(template).render({})
