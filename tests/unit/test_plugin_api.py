#!/usr/bin/env python
"""Tests for the supported plugin authoring API."""

import pytest

from ASOkai import plugin_api
from ASOkai._pipeline import registry
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

    assert set(plugin_api.__all__) == expected
    assert all(hasattr(plugin_api, name) for name in expected)


def test_plugin_steps_cannot_silently_replace_registered_names(monkeypatch):
    monkeypatch.setattr(
        registry,
        "_load_plugins",
        lambda group: [DownloadGenomeStep()] if group == "asokai.steps" else [],
    )

    with pytest.raises(ValueError, match="Duplicate registered step name"):
        registry.get_steps()
