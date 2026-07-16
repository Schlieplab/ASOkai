#!/usr/bin/env python
"""Tests for pipeline input resolution."""
from typing import ClassVar
from unittest.mock import patch

import pytest

from ASOkai._cwl.spec import InputParam, OutputParam, ScalarParam, StepSpec
from ASOkai._cwl.input_resolution import (
    resolve_step_inputs,
    resolve_step_sequence_inputs,
    to_cwl_inputs,
)
from ASOkai._pipeline.base import Step


class _FakeStep(Step):
    name = "fake-step"
    description = ""
    cli_module = "tests.fake_step"
    dependencies: ClassVar[list[str]] = []
    spec = StepSpec()

    def __init__(self, *, exists: bool = False) -> None:
        self._exists = exists

    def outputs_exist(self, config):
        return self._exists

    def cleanup(self, config):
        pass


def _fake_step(
    name: str,
    *,
    deps: list[str] | None = None,
    config_map: dict[str, str] | None = None,
    input_overrides: dict[str, str] | None = None,
    input_names: list[str] | None = None,
    output_names: list[str] | None = None,
    exists: bool = False,
) -> Step:
    """Return an isolated fake Step with class-level declaration metadata."""
    output_names = output_names or [f"{name}_out"]

    class ConfiguredFakeStep(_FakeStep):
        pass

    ConfiguredFakeStep.name = name
    ConfiguredFakeStep.dependencies = list(deps or [])
    ConfiguredFakeStep.spec = StepSpec(
        params=[
            ScalarParam(
                key,
                str,
                config=(config_map or {}).get(key),
            )
            for key in set(config_map or {}) - set(input_overrides or {})
        ],
        inputs=[
            InputParam(
                key,
                config=(config_map or {}).get(key),
                override=(input_overrides or {}).get(key),
            )
            for key in set(input_overrides or {}) | set(input_names or {})
        ],
        outputs=[
            OutputParam(
                key,
                temp_filename=f"{key}.txt",
                destination=f"{name}/{key}.txt",
            )
            for key in output_names
        ],
    )
    return ConfiguredFakeStep(exists=exists)


def test_resolve_step_inputs_input_override_beats_dep_output_and_scalar(tmp_path):
    config = {
        "datadir": str(tmp_path),
        "shared": {
            "scalar": "from-config",
            "override": str(tmp_path / "override.fa"),
        },
    }
    dep = _fake_step("dep", output_names=["shared"])
    step = _fake_step(
        "consumer",
        deps=["dep"],
        config_map={"shared": "shared.scalar"},
        input_overrides={"shared": "shared.override"},
    )

    with patch("ASOkai._cwl.input_resolution.get_steps", return_value={"dep": dep}):
        resolved = resolve_step_inputs(
            step,
            config,
            pre_resolved={"shared": tmp_path / "dep.fa"},
        )

    assert resolved["shared"].source == "input_override"
    assert resolved["shared"].cwl_value == {
        "class": "File",
        "path": str((tmp_path / "override.fa").resolve()),
    }


def test_resolve_step_inputs_wires_in_plan_dependency_outputs(tmp_path):
    config = {"datadir": str(tmp_path)}
    dep = _fake_step("dep", output_names=["dep_file"])
    step = _fake_step("consumer", deps=["dep"], input_names=["dep_file"])

    with patch("ASOkai._cwl.input_resolution.get_steps", return_value={"dep": dep}):
        resolved = resolve_step_inputs(
            step,
            config,
            steps_in_plan={"dep", "consumer"},
        )

    assert resolved["dep_file"].source == "dep_wired"
    assert resolved["dep_file"].cwl_value is None
    assert "dep_file" not in to_cwl_inputs(resolved)


def test_resolve_step_inputs_uses_pre_resolved_dependency_file(tmp_path):
    config = {"datadir": str(tmp_path)}
    dep = _fake_step("dep", output_names=["dep_file"])
    step = _fake_step("consumer", deps=["dep"], input_names=["dep_file"])
    path = tmp_path / "dep-output.txt"

    with patch("ASOkai._cwl.input_resolution.get_steps", return_value={"dep": dep}):
        resolved = resolve_step_inputs(
            step,
            config,
            pre_resolved={"dep_file": path},
        )

    assert resolved["dep_file"].source == "dep_disk"
    assert resolved["dep_file"].cwl_value == {
        "class": "File",
        "path": str(path.resolve()),
    }


def test_resolve_step_inputs_uses_dependency_output_path_without_pre_resolution(
    tmp_path,
):
    config = {"datadir": str(tmp_path)}
    dep = _fake_step("dep", output_names=["dep_file"])
    step = _fake_step("consumer", deps=["dep"], input_names=["dep_file"])

    with patch("ASOkai._cwl.input_resolution.get_steps", return_value={"dep": dep}):
        resolved = resolve_step_inputs(step, config)

    expected = dep.output_paths(config)["dep_file"]
    assert resolved["dep_file"].source == "dep_disk"
    assert resolved["dep_file"].cwl_value == {
        "class": "File",
        "path": str(expected.resolve()),
    }


def test_resolve_step_inputs_does_not_inject_output_filenames(tmp_path):
    config = {"datadir": str(tmp_path)}
    step = _fake_step("producer", output_names=["result"])

    resolved = resolve_step_inputs(step, config)

    assert "result_output" not in resolved
    assert "result_filename" not in resolved


def test_resolve_step_inputs_ignores_undeclared_dependency_outputs(tmp_path):
    config = {"datadir": str(tmp_path)}
    dep = _fake_step("dep", output_names=["unused"])
    step = _fake_step("consumer", deps=["dep"])

    with patch("ASOkai._cwl.input_resolution.get_steps", return_value={"dep": dep}):
        resolved = resolve_step_inputs(step, config, steps_in_plan={"dep", "consumer"})

    assert "unused" not in resolved


def test_resolve_step_sequence_rejects_conflicting_shared_inputs(tmp_path):
    config = {
        "datadir": str(tmp_path),
        "first": {"mode": "fast"},
        "second": {"mode": "careful"},
    }
    first = _fake_step("first", config_map={"mode": "first.mode"})
    second = _fake_step("second", config_map={"mode": "second.mode"})

    with pytest.raises(ValueError, match="input 'mode'.*conflicting values"):
        resolve_step_sequence_inputs([first, second], config, {})


def test_resolve_step_sequence_merges_matching_shared_inputs(tmp_path):
    config = {
        "datadir": str(tmp_path),
        "shared": {"mode": "fast"},
    }
    first = _fake_step("first", config_map={"mode": "shared.mode"})
    second = _fake_step("second", config_map={"mode": "shared.mode"})

    resolved = resolve_step_sequence_inputs([first, second], config, {})

    assert resolved["mode"] == "fast"
