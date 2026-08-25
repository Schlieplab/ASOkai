#!/usr/bin/env python
"""Tests for structured pipeline output-path templates."""

import pytest

from ASOkai._pipeline.contracts.paths import OutputPathTemplate, TemplateField


def test_output_path_renders_fallbacks_and_transforms():
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
    assert destination.input_names() == {
        "species",
        "target_id",
        "target_name",
    }


def test_output_path_rejects_unused_field_rules():
    with pytest.raises(ValueError, match="not used by the template"):
        OutputPathTemplate(
            "result.json",
            fields={"unused": TemplateField("value")},
        )


def test_output_path_requires_a_value_for_each_field():
    with pytest.raises(ValueError, match="No value is available"):
        OutputPathTemplate("{sample}.json").render({})


@pytest.mark.parametrize("template", ["../result.json", "/result.json"])
def test_output_path_must_stay_below_datadir(template):
    with pytest.raises(ValueError, match="stay below datadir"):
        OutputPathTemplate(template).render({})
