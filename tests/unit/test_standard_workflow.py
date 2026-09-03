#!/usr/bin/env python
"""
Filename: tests/unit/test_standard_workflow.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Tests for StandardWorkflow.
License: LGPL-3.0-or-later
"""

import pytest
from ASOkai._pipeline.workflows.standard import StandardWorkflow
from ASOkai.Plugins import Runnable, Step, Task, Workflow
from ASOkai._pipeline.base import expand_runnable_steps


@pytest.fixture
def workflow():
    return StandardWorkflow()


def test_standard_workflow_declaration(workflow):
    assert workflow.name == "standard"
    assert isinstance(workflow, Runnable)
    assert isinstance(workflow, Workflow)
    assert isinstance(workflow.members, tuple)
    assert all(isinstance(m, Runnable) for m in workflow.members)
    assert isinstance(workflow.members[0], Task)
    assert isinstance(workflow.members[0].steps, tuple)
    assert all(isinstance(member, Step) for member in workflow.members[1:])
    assert [m.name for m in workflow.members] == [
        "instantiate-target-gene",
        "generate-aso-candidates",
        "intrinsic-features",
    ]


def test_builtin_compositions_cannot_be_replaced(workflow):
    with pytest.raises(AttributeError):
        workflow.members = ()
    with pytest.raises(AttributeError):
        workflow.members[0].steps = ()


def test_flattens_to_explicit_step_names(workflow):
    assert [s.name for s in expand_runnable_steps(workflow)] == [
        "download-genome",
        "create-target-gene",
        "generate-aso-candidates",
        "intrinsic-features",
    ]
