#!/usr/bin/env python
"""Tests for the supported plugin authoring API."""

from ASOkai import plugin_api


def test_step_authoring_contracts_are_public() -> None:
    expected = {
        "AnalysisStep",
        "CoreStep",
        "CwlToolArgument",
        "InputParam",
        "OutputParam",
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
