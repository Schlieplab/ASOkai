#!/usr/bin/env python
"""
Filename: tests/unit/test_cwl_resources.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Version: 0.1.1
Description: Tests for translating resource configuration to CWL.
License: LGPL-3.0-or-later
"""

from ASOkai._cwl.resources import cwl_resource_requirement


def test_cwl_resource_requirement_translates_supported_fields():
    config = {
        "resources": {
            "analysis": {
                "n_processes": 4,
                "memory_mb": 8192,
            }
        }
    }

    assert cwl_resource_requirement(config, "analysis") == {
        "coresMin": 4,
        "ramMin": 8192,
    }


def test_cwl_resource_requirement_uses_pipeline_defaults():
    assert cwl_resource_requirement({}, "analysis") == {
        "coresMin": 1,
        "ramMin": 4096,
    }


def test_cwl_resource_requirement_prefers_authored_values_to_builtin_defaults():
    authored = {"coresMin": 8, "ramMin": 16384}

    assert cwl_resource_requirement({}, "analysis", authored) == authored


def test_cwl_resource_requirement_prefers_configuration_to_authored_values():
    config = {
        "resources": {
            "analysis": {
                "n_processes": 4,
                "memory_mb": 8192,
            }
        }
    }

    assert cwl_resource_requirement(
        config,
        "analysis",
        {"coresMin": 8, "ramMin": 16384},
    ) == {
        "coresMin": 4,
        "ramMin": 8192,
    }
