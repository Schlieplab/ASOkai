#!/usr/bin/env python
"""Tests for the pipeline catalog and installed-plugin discovery."""

from pathlib import Path
import runpy
import tomllib

import pytest

from ASOkai import Plugins
from ASOkai.Plugins import (
    AnalysisStep,
    CsvFile,
    FileInput,
    FileOutput,
    ScalarParam,
    Step,
    StepSpec,
)
from ASOkai._pipeline import catalog as pipeline_catalog
from ASOkai._pipeline.steps.core.download_genome import DownloadGenomeStep

ROOT = Path(__file__).parents[2]
EXAMPLE_PLUGIN = ROOT / "examples/plugins/example_analysis"
EXAMPLE_SCHEMA = EXAMPLE_PLUGIN / "src/asokai_example_analysis/config.schema.yaml"
EXAMPLE_STEP_CLASS = runpy.run_path(
    str(EXAMPLE_PLUGIN / "src/asokai_example_analysis/analysis_step.py")
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
        self.load_count = 0

    def load(self):
        self.load_count += 1
        if self.load_error is not None:
            raise self.load_error
        return self.value


def _provide_entry_points(monkeypatch, *provided: FakeEntryPoint) -> None:
    monkeypatch.setattr(
        pipeline_catalog,
        "entry_points",
        lambda *, group: [
            entry_point for entry_point in provided if entry_point.group == group
        ],
    )


class UndeclaredConfigStep(Step):
    name = "undeclared-config"
    description = "Uses a configuration field without a plugin schema."
    result_output = FileOutput("result", destination="undeclared/result.txt")
    spec = StepSpec(
        params=[
            ScalarParam(
                "threshold",
                int,
                config="undeclared.threshold",
            ),
        ],
        compatible_with={
            "undeclared.mode": ["fast"],
        },
        outputs=[result_output],
    )

    def run_from_args(self, args) -> int:
        return 0


class ConstructorFailureStep(Step):
    name = "constructor-failure"
    description = "Raises while being instantiated."
    result_output = FileOutput("result", destination="constructor/result.txt")
    spec = StepSpec(outputs=[result_output])

    def __init__(self) -> None:
        raise RuntimeError("initialization failed")

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
    result_output = FileOutput("consumer_result", destination="consumer/result.txt")
    spec = StepSpec(inputs=[result_input], outputs=[result_output])

    def run_from_args(self, args) -> int:
        return 0


class InvalidAnalysisStep(AnalysisStep):
    name = "invalid-analysis"
    description = "Does not declare an analysis implementation."
    result_output = FileOutput(
        "result",
        destination="invalid-analysis/result.csv",
        file_type=CsvFile(index={"site_id": str}, columns={"value": int}),
    )
    spec = StepSpec(outputs=[result_output])


class PluginTaskWithUnregisteredStep:
    name = "unregistered-task"
    description = "Contains a step that was not registered."
    steps = [UnregisteredProducerStep()]


class PluginWorkflowWithUnregisteredTask:
    name = "unregistered-workflow"
    description = "Contains a task that was not registered."
    members = [PluginTaskWithUnregisteredStep()]


class RegisteredPluginStep(Step):
    name = "registered-plugin-step"
    description = "A valid step used to exercise aggregate discovery."
    result_output = FileOutput("result", destination="registered/result.txt")
    spec = StepSpec(outputs=[result_output])

    def run_from_args(self, args) -> int:
        return 0


class RegisteredPluginTask:
    name = "registered-plugin-task"
    description = "A valid plugin task."
    steps = [RegisteredPluginStep()]


class RegisteredPluginWorkflow:
    name = "registered-plugin-workflow"
    description = "A valid plugin workflow."
    members = [RegisteredPluginTask()]


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
        "GenerateASOCandidatesStep",
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

    registered = pipeline_catalog.get_steps()

    assert isinstance(
        registered["example-sequence-length"],
        EXAMPLE_STEP_CLASS,
    )


def test_pipeline_catalog_loads_each_plugin_once(monkeypatch) -> None:
    step_entry_point = FakeEntryPoint(
        "asokai.steps",
        RegisteredPluginStep.name,
        RegisteredPluginStep,
    )
    task_entry_point = FakeEntryPoint(
        "asokai.tasks",
        RegisteredPluginTask.name,
        RegisteredPluginTask,
    )
    workflow_entry_point = FakeEntryPoint(
        "asokai.workflows",
        RegisteredPluginWorkflow.name,
        RegisteredPluginWorkflow,
    )
    schema_entry_point = FakeEntryPoint(
        "asokai.config_schemas",
        "registered-plugin-schema",
        EXAMPLE_SCHEMA,
    )
    _provide_entry_points(
        monkeypatch,
        step_entry_point,
        task_entry_point,
        workflow_entry_point,
        schema_entry_point,
    )

    catalog = pipeline_catalog.get_pipeline_catalog()

    assert RegisteredPluginStep.name in catalog.steps
    assert RegisteredPluginTask.name in catalog.tasks
    assert RegisteredPluginWorkflow.name in catalog.workflows
    assert step_entry_point.load_count == 1
    assert task_entry_point.load_count == 1
    assert workflow_entry_point.load_count == 1
    assert schema_entry_point.load_count == 1


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
        pipeline_catalog.get_steps()


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
        pipeline_catalog.get_steps()


def test_plugin_entry_point_must_expose_expected_class(monkeypatch) -> None:
    _provide_entry_points(
        monkeypatch,
        FakeEntryPoint("asokai.steps", "not-a-class", object()),
    )

    with pytest.raises(ValueError, match="must expose a class"):
        pipeline_catalog.get_steps()


def test_plugin_class_must_implement_the_entry_point_kind(monkeypatch) -> None:
    _provide_entry_points(
        monkeypatch,
        FakeEntryPoint("asokai.steps", "wrong-kind", object),
    )

    with pytest.raises(ValueError, match="expected Step, received object"):
        pipeline_catalog.get_steps()


def test_plugin_instantiation_errors_include_entry_point_context(monkeypatch) -> None:
    _provide_entry_points(
        monkeypatch,
        FakeEntryPoint(
            "asokai.steps",
            ConstructorFailureStep.name,
            ConstructorFailureStep,
            package="broken-constructor-package",
        ),
    )

    with pytest.raises(
        ValueError,
        match=r"constructor-failure.*broken-constructor-package.*initialization failed",
    ):
        pipeline_catalog.get_steps()


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
        pipeline_catalog.get_steps()


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
        pipeline_catalog.get_steps()


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
        pipeline_catalog.get_steps()


def test_plugin_config_paths_require_a_registered_schema(monkeypatch) -> None:
    _provide_entry_points(
        monkeypatch,
        FakeEntryPoint(
            "asokai.steps",
            "undeclared-config",
            UndeclaredConfigStep,
        ),
    )

    with pytest.raises(ValueError) as raised:
        pipeline_catalog.get_steps()

    message = str(raised.value)
    assert "undeclared.threshold" in message
    assert "undeclared.mode" in message
    assert "no registered configuration schema" in message


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
        pipeline_catalog.get_steps()


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
        pipeline_catalog.get_tasks()


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
        pipeline_catalog.get_workflows()


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

    assert pipeline_catalog.get_config_schema_paths() == {
        "example": schema_path,
    }


def test_plugin_config_schema_names_must_be_unique(monkeypatch, tmp_path) -> None:
    _provide_entry_points(
        monkeypatch,
        FakeEntryPoint(
            "asokai.config_schemas",
            "duplicate",
            tmp_path / "first.yaml",
        ),
        FakeEntryPoint(
            "asokai.config_schemas",
            "duplicate",
            tmp_path / "second.yaml",
        ),
    )

    with pytest.raises(ValueError, match="Duplicate registered config schema"):
        pipeline_catalog.get_config_schema_paths()
