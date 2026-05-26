"""Tests for pipeline input resolution."""
from pathlib import Path
from unittest.mock import patch

from pipeline.input_resolution import resolve_step_inputs, to_cwl_inputs


class _FakeStep:
    def __init__(
        self,
        name,
        *,
        deps=None,
        config_map=None,
        input_overrides=None,
        output_names=None,
        output_inputs=None,
        exists=False,
    ):
        self.name = name
        self.description = ""
        self.cli_module = "tests.fake_step"
        self.dependencies = list(deps or [])
        self.config_map = dict(config_map or {})
        self.input_overrides = dict(input_overrides or {})
        self._output_names = tuple(output_names or [f"{name}_out"])
        self._exists = exists
        if output_inputs is not None:
            self.output_inputs = output_inputs

    @property
    def cwl_path(self):
        return f"/fake/{self.name}.cwl"

    def outdir(self, config):
        return Path(config["datadir"]) / self.name

    def output_paths(self, config):
        base = self.outdir(config)
        return {key: base / f"{key}.txt" for key in self._output_names}

    def outputs_exist(self, _config):
        return self._exists

    def cleanup(self, _config):
        pass


def test_resolve_step_inputs_input_override_beats_dep_output_and_scalar(tmp_path):
    config = {
        "datadir": str(tmp_path),
        "shared": {
            "scalar": "from-config",
            "override": str(tmp_path / "override.fa"),
        },
    }
    dep = _FakeStep("dep", output_names=["shared"])
    step = _FakeStep(
        "consumer",
        deps=["dep"],
        config_map={"shared": "shared.scalar"},
        input_overrides={"shared": "shared.override"},
    )

    with patch("pipeline.input_resolution.get_steps", return_value={"dep": dep}):
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
    dep = _FakeStep("dep", output_names=["dep_file"])
    step = _FakeStep("consumer", deps=["dep"])

    with patch("pipeline.input_resolution.get_steps", return_value={"dep": dep}):
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
    dep = _FakeStep("dep", output_names=["dep_file"])
    step = _FakeStep("consumer", deps=["dep"])
    path = tmp_path / "dep-output.txt"

    with patch("pipeline.input_resolution.get_steps", return_value={"dep": dep}):
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


def test_resolve_step_inputs_auto_injects_output_filename(tmp_path):
    config = {"datadir": str(tmp_path)}
    step = _FakeStep("producer", output_names=["result"])

    resolved = resolve_step_inputs(step, config)

    assert resolved["result_output"].source == "output_path"
    assert resolved["result_output"].cwl_value == "result.txt"


def test_resolve_step_inputs_respects_output_input_opt_out(tmp_path):
    config = {"datadir": str(tmp_path)}
    step = _FakeStep("producer", output_names=["result"], output_inputs={})

    resolved = resolve_step_inputs(step, config)

    assert "result_output" not in resolved
