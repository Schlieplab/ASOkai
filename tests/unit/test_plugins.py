#!/usr/bin/env python
"""Tests for extension authoring and discovery."""

from pathlib import Path

import pytest

from ASOkai import Plugins
from ASOkai.Plugins import _registry as plugin_registry
from ASOkai._pipeline.steps.core.download_genome import DownloadGenomeStep


def test_step_authoring_contracts_are_public() -> None:
    expected = {
        "AnalysisStep",
        "CoreStep",
        "CwlToolArgument",
        "CsvFile",
        "FileInput",
        "FileOutput",
        "FileType",
        "JsonFile",
        "OutputPathTemplate",
        "Runnable",
        "ScalarParam",
        "Step",
        "StepSpec",
        "Task",
        "TemplateField",
        "Workflow",
    }

    assert set(Plugins.__all__) == expected
    assert all(hasattr(Plugins, name) for name in expected)


def test_plugin_steps_cannot_silently_replace_registered_names(monkeypatch):
    monkeypatch.setattr(
        plugin_registry,
        "_load_plugins",
        lambda group: [DownloadGenomeStep()] if group == "asokai.steps" else [],
    )

    with pytest.raises(ValueError, match="Duplicate registered step name"):
        plugin_registry.get_steps()


def test_plugin_config_schema_entry_points_expose_paths(
    monkeypatch,
    tmp_path,
):
    schema_path = tmp_path / "config.schema.yaml"

    class ConfigSchemaEntryPoint:
        name = "example"

        @staticmethod
        def load():
            return schema_path

    monkeypatch.setattr(
        plugin_registry,
        "entry_points",
        lambda *, group: (
            [ConfigSchemaEntryPoint()]
            if group == "asokai.config_schemas"
            else []
        ),
    )

    assert plugin_registry.get_config_schema_paths() == {
        "example": Path(schema_path),
    }
