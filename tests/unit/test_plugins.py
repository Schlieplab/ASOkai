#!/usr/bin/env python
"""Tests for extension authoring and discovery."""

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
