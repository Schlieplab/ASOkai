#!/usr/bin/env python
"""Tests for external extension authoring, discovery, and validation."""

from pathlib import Path
import runpy
import tomllib

import pytest

from ASOkai import Plugins
from ASOkai.Plugins import (
    AnalysisStep,
    FileInput,
    FileOutput,
    ScalarParam,
    Step,
    StepSpec,
)
from ASOkai.Plugins import _registry as plugin_registry
from ASOkai._pipeline.steps.core.download_genome import DownloadGenomeStep


ROOT = Path(__file__).parents[2]
EXAMPLE_PLUGIN = ROOT / "examples/plugins/example_analysis"
EXAMPLE_SCHEMA = (
    EXAMPLE_PLUGIN
    / "src/asokai_example_analysis/config.schema.yaml"
)
EXAMPLE_STEP_CLASS = runpy.run_path(
    str(
        EXAMPLE_PLUGIN
        / "src/asokai_example_analysis/analysis_step.py"
    )
)["ExampleAnalysisStep"]


class FakeDistribution:
    def __init__(self, name: str) -> None:
        self.name = name


class FakeEntryPoint:
    def __init__(
        self,
        group: str,
        name: str,
        value,
        *,
        package: str = "asokai-test-plugin",
        load_error: Exception | None = None,
    ) -> None:
        self.group = group
        self.name = name
        self.value = value
        self.dist = FakeDistribution(package)
        self.load_error = load_error

    def load(self):
        if self.load_error is not None:
            raise self.load_error
        return self.value


def _provide_entry_points(monkeypatch, *provided: FakeEntryPoint) -> None:
    monkeypatch.setattr(
        plugin_registry,
        "entry_points",
        lambda *, group: [
            entry_point
            for entry_point in provided
            if entry_point.group == group
        ],
    )


class UndeclaredConfigStep(Step):
    name = "undeclared-config"
    description = "Uses a configuration field without a plugin schema."
    spec = StepSpec(
        params=[
            ScalarParam(
                "threshold",
                int,
                config="undeclared.threshold",
            ),
        ],
    )

    def run_from_args(self, args) -> int:
        return 0


class UnregisteredProducerStep(Step):
    name = "unregistered-producer"
    description = "Produces an output without being registered."
    result_output = FileOutput(
        "result",
        destination="plugin/unregistered.txt",
    )
    spec = StepSpec(outputs=[result_output])

    def run_from_args(self, args) -> int:
        return 0


class MissingProducerStep(Step):
    name = "missing-producer"
    description = "Depends on an unregistered producer."
    result_input = FileInput(
        "result",
        source=UnregisteredProducerStep.result_output,
    )
    spec = StepSpec(inputs=[result_input])

    def run_from_args(self, args) -> int:
        return 0


class InvalidAnalysisStep(AnalysisStep):
    name = "invalid-analysis"
    description = "Does not declare an analysis implementation."
    spec = StepSpec()


class PluginTaskWithUnregisteredStep:
    name = "unregistered-task"
    description = "Contains a step that was not registered."
    steps = [UnregisteredProducerStep()]

    def output_paths(self, config: dict) -> dict:
        return {}

    def outputs_exist(self, config: dict) -> bool:
        return False

    def cleanup(self, config: dict) -> None:
        return None


class PluginWorkflowWithUnregisteredTask:
    name = "unregistered-workflow"
    description = "Contains a task that was not registered."
    members = [PluginTaskWithUnregisteredStep()]

    def output_paths(self, config: dict) -> dict:
        return {}

    def outputs_exist(self, config: dict) -> bool:
        return False

    def cleanup(self, config: dict) -> None:
        return None


def test_step_authoring_contracts_are_public() -> None:
    expected = {
        "AnalysisStep",
        "CreateTargetGeneStep",
        "CoreStep",
        "CwlToolArgument",
        "CsvFile",
        "DownloadGenomeStep",
        "FileInput",
        "FileOutput",
        "FileType",
        "GenerateAntisenseCandidatesStep",
        "IntrinsicFeaturesStep",
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


def test_example_plugin_declares_installable_entry_points() -> None:
    metadata = tomllib.loads(
        (EXAMPLE_PLUGIN / "pyproject.toml").read_text(encoding="utf-8")
    )

    assert metadata["project"]["entry-points"]["asokai.steps"] == {
        "example-sequence-length": (
            "asokai_example_analysis.analysis_step:ExampleAnalysisStep"
        ),
    }
    assert metadata["project"]["entry-points"]["asokai.config_schemas"] == {
        "example-analysis": "asokai_example_analysis:CONFIG_SCHEMA_PATH",
    }


def test_example_plugin_is_discovered_and_validated(monkeypatch) -> None:
    _provide_entry_points(
        monkeypatch,
        FakeEntryPoint(
            "asokai.steps",
            "example-sequence-length",
            EXAMPLE_STEP_CLASS,
            package="asokai-example-analysis",
        ),
        FakeEntryPoint(
            "asokai.config_schemas",
            "example-analysis",
            EXAMPLE_SCHEMA,
            package="asokai-example-analysis",
        ),
    )

    registered = plugin_registry.get_steps()

    assert isinstance(
        registered["example-sequence-length"],
        EXAMPLE_STEP_CLASS,
    )


def test_plugin_steps_cannot_replace_registered_names(monkeypatch) -> None:
    _provide_entry_points(
        monkeypatch,
        FakeEntryPoint(
            "asokai.steps",
            "download-genome",
            DownloadGenomeStep,
        ),
    )

    with pytest.raises(ValueError, match="Duplicate registered step name"):
        plugin_registry.get_steps()


def test_plugin_load_errors_include_package_context(monkeypatch) -> None:
    _provide_entry_points(
        monkeypatch,
        FakeEntryPoint(
            "asokai.steps",
            "broken",
            object,
            package="broken-package",
            load_error=ModuleNotFoundError("missing dependency"),
        ),
    )

    with pytest.raises(
        ValueError,
        match=r"broken.*broken-package.*missing dependency",
    ):
        plugin_registry.get_steps()


def test_plugin_entry_point_must_expose_expected_class(monkeypatch) -> None:
    _provide_entry_points(
        monkeypatch,
        FakeEntryPoint("asokai.steps", "not-a-class", object()),
    )

    with pytest.raises(ValueError, match="must expose a class"):
        plugin_registry.get_steps()


def test_plugin_entry_point_name_must_match_step_name(monkeypatch) -> None:
    _provide_entry_points(
        monkeypatch,
        FakeEntryPoint(
            "asokai.steps",
            "different-name",
            UndeclaredConfigStep,
        ),
    )

    with pytest.raises(ValueError, match="must match.*undeclared-config"):
        plugin_registry.get_steps()


def test_analysis_plugin_contract_is_validated(monkeypatch) -> None:
    _provide_entry_points(
        monkeypatch,
        FakeEntryPoint(
            "asokai.steps",
            "invalid-analysis",
            InvalidAnalysisStep,
        ),
    )

    with pytest.raises(ValueError, match="concrete Analysis subclass"):
        plugin_registry.get_steps()


def test_plugin_dependencies_must_be_registered(monkeypatch) -> None:
    _provide_entry_points(
        monkeypatch,
        FakeEntryPoint(
            "asokai.steps",
            "missing-producer",
            MissingProducerStep,
        ),
    )

    with pytest.raises(ValueError, match="unregistered producer"):
        plugin_registry.get_steps()


def test_plugin_config_paths_require_a_registered_schema(monkeypatch) -> None:
    _provide_entry_points(
        monkeypatch,
        FakeEntryPoint(
            "asokai.steps",
            "undeclared-config",
            UndeclaredConfigStep,
        ),
    )

    with pytest.raises(
        ValueError,
        match=r"undeclared\.threshold.*no registered configuration schema",
    ):
        plugin_registry.get_steps()


def test_plugin_config_schema_must_come_from_the_same_package(
    monkeypatch,
    tmp_path,
) -> None:
    schema_path = tmp_path / "config.schema.yaml"
    schema_path.write_text(
        "type: object\n"
        "properties:\n"
        "  undeclared:\n"
        "    type: object\n"
        "    properties:\n"
        "      threshold:\n"
        "        type: integer\n",
        encoding="utf-8",
    )
    _provide_entry_points(
        monkeypatch,
        FakeEntryPoint(
            "asokai.steps",
            "undeclared-config",
            UndeclaredConfigStep,
            package="step-package",
        ),
        FakeEntryPoint(
            "asokai.config_schemas",
            "unrelated-schema",
            schema_path,
            package="different-package",
        ),
    )

    with pytest.raises(ValueError, match="undeclared\\.threshold"):
        plugin_registry.get_steps()


def test_plugin_task_steps_must_be_registered(monkeypatch) -> None:
    _provide_entry_points(
        monkeypatch,
        FakeEntryPoint(
            "asokai.tasks",
            "unregistered-task",
            PluginTaskWithUnregisteredStep,
        ),
    )

    with pytest.raises(ValueError, match="asokai.steps"):
        plugin_registry.get_tasks()


def test_plugin_workflow_members_must_be_registered(monkeypatch) -> None:
    _provide_entry_points(
        monkeypatch,
        FakeEntryPoint(
            "asokai.workflows",
            "unregistered-workflow",
            PluginWorkflowWithUnregisteredTask,
        ),
    )

    with pytest.raises(ValueError, match="asokai.tasks"):
        plugin_registry.get_workflows()


def test_plugin_config_schema_entry_points_expose_paths(
    monkeypatch,
    tmp_path,
) -> None:
    schema_path = tmp_path / "config.schema.yaml"
    _provide_entry_points(
        monkeypatch,
        FakeEntryPoint(
            "asokai.config_schemas",
            "example",
            schema_path,
        ),
    )

    assert plugin_registry.get_config_schema_paths() == {
        "example": schema_path,
    }
