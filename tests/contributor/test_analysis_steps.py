#!/usr/bin/env python
"""Repository checks for built-in analysis-step contributions."""

from __future__ import annotations

import importlib
import inspect
import pkgutil
import runpy
from pathlib import Path
from typing import Any, Mapping, cast

import pytest
import yaml

from ASOkai.Analysis import Analysis
from ASOkai.Plugins import AnalysisStep, CsvFile, JsonFile, Step
from ASOkai.Plugins import _registry as registry
from ASOkai._pipeline import config as config_module
from ASOkai._pipeline import steps as steps_package
from ASOkai._pipeline.contracts.json_schema import (
    JsonSchema,
    build_json_schema,
    json_schema_errors,
)


ROOT = Path(__file__).parents[2]


def _load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, Mapping), f"{path} must contain a YAML mapping."
    return dict(data)


CORE_SCHEMA = cast(
    JsonSchema,
    _load_yaml(ROOT / "src/ASOkai/_pipeline/config.schema.yaml"),
)
EXAMPLE_CONFIG = _load_yaml(ROOT / "examples/config.example.yaml")
TEMPLATE_STEP = cast(
    type[AnalysisStep],
    runpy.run_path(
        str(ROOT / "examples/contributor_steps/analysis_step.py")
    )["ExampleAnalysisStep"],
)()
BUILTIN_STEPS = tuple(registry._BUILTIN_STEPS)
CONTRIBUTOR_STEPS = (*BUILTIN_STEPS, TEMPLATE_STEP)
REGISTERED_STEPS = {step.name: step for step in BUILTIN_STEPS}


def _concrete_step_classes() -> set[type[Step]]:
    classes: set[type[Step]] = set()
    for module_info in pkgutil.walk_packages(
        steps_package.__path__,
        f"{steps_package.__name__}.",
    ):
        if module_info.name.endswith(".base"):
            continue
        module = importlib.import_module(module_info.name)
        classes.update(
            value
            for value in vars(module).values()
            if inspect.isclass(value)
            and value.__module__ == module.__name__
            and issubclass(value, Step)
        )
    return classes


def _step_name(step: Step) -> str:
    return type(step).__name__


def test_example_config_supports_every_contributor_step() -> None:
    errors = json_schema_errors(CORE_SCHEMA, EXAMPLE_CONFIG)
    assert not errors, (
        "Invalid examples/config.example.yaml:\n- " + "\n- ".join(errors)
    )
    config_module.validate_step_config(EXAMPLE_CONFIG, CONTRIBUTOR_STEPS)


def test_every_concrete_step_is_registered_once() -> None:
    registered_classes = {type(step) for step in BUILTIN_STEPS}
    concrete_classes = _concrete_step_classes()
    names = [step.name for step in BUILTIN_STEPS]
    assert len(names) == len(set(names)), "Built-in step names must be unique."
    assert registered_classes == concrete_classes, (
        "Built-in step registration is incomplete. Missing: "
        f"{sorted(cls.__name__ for cls in concrete_classes - registered_classes)}; "
        "unexpected: "
        f"{sorted(cls.__name__ for cls in registered_classes - concrete_classes)}."
    )


@pytest.mark.parametrize("step", CONTRIBUTOR_STEPS, ids=_step_name)
def test_step_config_paths_exist_in_core_schema(step: Step) -> None:
    config_module.validate_step_config_paths([step])


@pytest.mark.parametrize("step", CONTRIBUTOR_STEPS, ids=_step_name)
def test_step_dependencies_use_registered_outputs(step: Step) -> None:
    for file_input in step.spec.inputs:
        producer = REGISTERED_STEPS.get(file_input.source.producer)
        assert producer is not None, (
            f"{type(step).__name__}.{file_input.name} references an "
            "unregistered producer."
        )
        assert producer.spec.output(file_input.source.name) is file_input.source, (
            f"{type(step).__name__}.{file_input.name} must reference the "
            "registered producer output declaration."
        )


@pytest.mark.parametrize("step", CONTRIBUTOR_STEPS, ids=_step_name)
def test_step_contract_builds_from_example_config(step: Step) -> None:
    step.build_parser()
    step.cwl_spec(EXAMPLE_CONFIG)
    step.validated_output_paths(EXAMPLE_CONFIG)
    for output in step.spec.outputs:
        if isinstance(output.file_type, JsonFile) and output.file_type.value_type:
            build_json_schema(output.file_type.value_type)


@pytest.mark.parametrize(
    "step",
    [step for step in CONTRIBUTOR_STEPS if isinstance(step, AnalysisStep)],
    ids=_step_name,
)
def test_analysis_step_contract(step: AnalysisStep) -> None:
    name = type(step).__name__
    assert step.analysis_cls is not None, f"{name} must declare analysis_cls."
    assert issubclass(step.analysis_cls, Analysis), (
        f"{name}.analysis_cls must inherit Analysis."
    )
    assert len(step.spec.outputs) == 1, (
        f"{name} must declare exactly one output."
    )
    output = step.spec.outputs[0]
    assert isinstance(output.file_type, CsvFile), (
        f"{name}.{output.name} must use CsvFile."
    )
    assert len(output.file_type.index) == 1, (
        f"{name}.{output.name} must declare one CSV index."
    )
