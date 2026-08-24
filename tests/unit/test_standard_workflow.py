#!/usr/bin/env python
"""
Filename: tests/unit/test_standard_workflow.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Version: 0.1.1
Description: Tests for StandardWorkflow.
License: LGPL-3.0-or-later
"""

import pytest
from ASOkai._pipeline.workflows.standard import StandardWorkflow
from ASOkai.Plugins import Runnable, Step, Workflow
from ASOkai._pipeline.plan import _flatten_goals


@pytest.fixture
def workflow():
    return StandardWorkflow()


def test_name(workflow):
    assert workflow.name == "standard"


def test_implements_runnable(workflow):
    assert isinstance(workflow, Runnable)


def test_implements_workflow_protocol(workflow):
    assert isinstance(workflow, Workflow)


def test_members_are_runnables(workflow):
    assert all(isinstance(m, Runnable) for m in workflow.members)
    assert all(isinstance(member, Step) for member in workflow.members)


def test_member_names(workflow):
    assert [m.name for m in workflow.members] == [
        "generate-antisense-candidates",
        "intrinsic-features",
    ]


def test_flattens_to_goal_names(workflow):
    assert [s.name for s in _flatten_goals(workflow)] == [
        "generate-antisense-candidates",
        "intrinsic-features",
    ]
