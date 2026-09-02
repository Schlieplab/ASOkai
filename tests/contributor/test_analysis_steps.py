#!/usr/bin/env python
"""Repository checks for built-in analysis-step contributions."""

from __future__ import annotations

from copy import deepcopy
import importlib
import inspect
import pkgutil
import runpy
from pathlib import Path
from typing import Any, Mapping, cast

import pytest
import yaml

from ASOkai.Plugins import AnalysisStep, JsonFile, Step
from ASOkai._pipeline.validation import (
    validate_component,
    validate_step_dependencies,
)
from ASOkai._pipeline import catalog as pipeline_catalog
from ASOkai._pipeline import config as config_module
from ASOkai._pipeline import steps as steps_package
from ASOkai._pipeline.contracts.json_schema import (
    JsonSchema,
    build_json_schema,
    json_schema_errors,
)
from ASOkai._pipeline.contracts.execution import StepRunOutput
from ASOkai._pipeline.plan import build_export_plan


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
BUILTIN_STEPS = tuple(pipeline_catalog._BUILTIN_STEPS)
CONTRIBUTOR_STEPS = (*BUILTIN_STEPS, TEMPLATE_STEP)
REGISTERED_STEPS = {step.name: step for step in BUILTIN_STEPS}
CONTRIBUTOR_REGISTRY = {
    **REGISTERED_STEPS,
    TEMPLATE_STEP.name: TEMPLATE_STEP,
}


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
    validate_step_dependencies(step, REGISTERED_STEPS)


@pytest.mark.parametrize("step", CONTRIBUTOR_STEPS, ids=_step_name)
def test_step_contract_builds_from_example_config(step: Step) -> None:
    validate_component("step", step)
    plan = build_export_plan(
        [step],
        EXAMPLE_CONFIG,
        recursive=True,
        _registry=CONTRIBUTOR_REGISTRY,
    )
    for run in plan.runs_to_execute:
        run.cwl_spec()
        run.output_paths()
    for output in step.spec.outputs:
        if isinstance(output.file_type, JsonFile) and output.file_type.value_type:
            build_json_schema(output.file_type.value_type)


def test_target_wide_example_can_select_an_alternate_target_region() -> None:
    config = deepcopy(EXAMPLE_CONFIG)
    config.setdefault("steps", {})[TEMPLATE_STEP.name] = {
        "inputs": {
            "target": {
                "parameters": {"region": "exonic"},
            },
        },
    }
    plan = build_export_plan(
        [TEMPLATE_STEP],
        config,
        recursive=True,
        _registry=CONTRIBUTOR_REGISTRY,
    )
    example_run = plan.goals[0]
    bindings = {
        binding.file_input.name: binding.source
        for binding in example_run.inputs
    }

    assert isinstance(bindings["sites"], StepRunOutput)
    assert isinstance(bindings["target"], StepRunOutput)
    assert bindings["sites"].run.run_id == "create-target-gene"
    assert bindings["target"].run.run_id == (
        "example-analysis.create-target-gene"
    )
    assert bindings["sites"].run.config["target"]["region"] == "pre-mrna"
    assert bindings["target"].run.config["target"]["region"] == "exonic"
    assert example_run.output_paths()["analysis"].name == (
        "ENSG00000133703_k16_pre-mrna_against_exonic_example.csv"
    )
