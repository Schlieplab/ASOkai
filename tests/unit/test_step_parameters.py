#!/usr/bin/env python
"""
Filename: tests/unit/test_step_parameters.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Tests for invocation parameters and their shared configuration fallback.
License: LGPL-3.0-or-later
"""

from copy import deepcopy
from typing import Literal

import pytest
import yaml

from ASOkai.Plugins import (
    FileOutput,
    OutputPathTemplate,
    ScalarParam,
    Step,
    StepSpec,
    TemplateField,
)
from ASOkai._cwl.generation import StepCwlGenerator, generate_cwl_bundle
from ASOkai._cwl.input_resolution import (
    resolve_run_inputs,
    resolve_run_sequence_inputs,
    to_cwl_inputs,
)
from ASOkai._pipeline import config as cfg
from ASOkai._pipeline.contracts.execution import StepRun
from ASOkai._pipeline.output_receipts import (
    record_validated_outputs,
    reusable_output_paths,
)
from ASOkai._pipeline.plan import build_export_plan


class ParameterStep(Step):
    name = "parameter-values"
    description = "Exercise invocation values, shared fallback, and defaults."
    result_output = FileOutput(
        "result",
        destination=OutputPathTemplate(
            "results/{mode}.txt", fields={"mode": TemplateField("shared.mode")}
        ),
    )
    spec = StepSpec(
        params=[
            ScalarParam(
                "mode", Literal["fast", "slow"], config="shared.mode", default="fast"
            ),
            ScalarParam("count", int, config="shared.count", default=8),
            ScalarParam("enabled", bool, config="shared.enabled"),
            ScalarParam("label", str | None, config="shared.label", default="fallback"),
            ScalarParam("local", int, default=5),
        ],
        outputs=[result_output],
    )


class RequiredParameterStep(Step):
    name = "required-parameter"
    description = "Require an invocation-only parameter."
    spec = StepSpec(params=[ScalarParam("count", int)])


class RangeStep(Step):
    name = "parameter-range"
    description = "Validate a relationship between invocation-only parameters."
    spec = StepSpec(
        params=[
            ScalarParam("minimum", int, default=0),
            ScalarParam("maximum", int, default=10),
        ],
    )

    def validate_parameters(self, values):
        if values["minimum"] > values["maximum"]:
            raise ValueError("minimum must not exceed maximum")


class SharedFallbackStep(Step):
    name = "shared-fallback"
    description = "Share a fallback between two scalar parameters."
    result_output = FileOutput(
        "result",
        destination=OutputPathTemplate(
            "results/{size}.txt", fields={"size": TemplateField("shared.size")}
        ),
    )
    spec = StepSpec(
        params=[
            ScalarParam("first_size", int, config="shared.size", default=10),
            ScalarParam("second_size", int, config="shared.size", default=10),
        ],
        outputs=[result_output],
    )


def test_resolution_uses_invocation_then_global_then_default():
    step = ParameterStep()
    config = {"shared": {"mode": "slow", "count": 12}, "local": 99}

    assert step.resolved_parameter_values(config, {"count": 21}) == {
        "mode": "slow",
        "count": 21,
        "enabled": False,
        "label": "fallback",
        "local": 5,
    }


def test_explicit_false_zero_and_null_override_global_values(tmp_path):
    config = {
        "datadir": str(tmp_path),
        "shared": {"enabled": True, "count": 12, "label": "global"},
    }
    run = StepRun(
        "override",
        ParameterStep(),
        config,
        parameters={
            "enabled": False,
            "count": 0,
            "label": None,
        },
    )

    assert run.parameters["enabled"] is False
    assert run.parameters["count"] == 0
    assert run.parameters["label"] is None
    assert to_cwl_inputs(resolve_run_inputs(run))["label"] is None
    assert resolve_run_sequence_inputs([run], {})["override.label"] is None


def test_runs_snapshot_values_without_mutating_shared_config(tmp_path):
    config = {"datadir": str(tmp_path), "shared": {"mode": "fast", "count": 12}}
    original = deepcopy(config)
    parameters = {"mode": "slow", "local": 7}
    step = ParameterStep()
    first = StepRun("first", step, config, parameters=parameters)
    second = StepRun("second", step, config)

    assert config == original
    assert first.output_paths()["result"] == tmp_path / "results/slow.txt"
    assert second.output_paths()["result"] == tmp_path / "results/fast.txt"
    assert first.parameters == {
        "mode": "slow",
        "local": 7,
        "count": 12,
        "enabled": False,
        "label": "fallback",
    }
    assert first.config["shared"]["mode"] == "slow"
    assert second.config["shared"]["mode"] == "fast"
    parameters["local"] = 100
    config["shared"]["count"] = 100
    assert first.parameters["local"] == 7
    assert second.parameters["count"] == 12
    with pytest.raises(TypeError):
        first.parameters["local"] = 1


@pytest.mark.parametrize("value", [None, True, "21"])
def test_invalid_invocation_value_does_not_fall_back(value):
    with pytest.raises(ValueError, match="parameter 'count'"):
        StepRun(
            "invalid",
            ParameterStep(),
            {"shared": {"count": 12}},
            parameters={"count": value},
        )


@pytest.mark.parametrize("value", [None, True, "21"])
def test_invalid_global_value_does_not_fall_back(value):
    with pytest.raises(ValueError, match="parameter 'count'"):
        ParameterStep().resolved_parameter_values({"shared": {"count": value}})


def test_invocation_can_replace_an_invalid_global_parameter():
    values = ParameterStep().resolved_parameter_values(
        {"shared": {"count": "invalid"}}, {"count": 21}
    )
    assert values["count"] == 21


def test_unknown_invocation_parameter_is_rejected():
    with pytest.raises(ValueError, match="unknown parameter.*coutn"):
        StepRun("invalid", ParameterStep(), {}, parameters={"coutn": 21})


def test_invocation_parameters_must_be_a_mapping():
    with pytest.raises(TypeError, match="parameters must be a mapping"):
        StepRun("invalid", ParameterStep(), {}, parameters=[])


def test_required_parameter_without_global_binding_requires_an_invocation_value():
    with pytest.raises(ValueError, match="count.*requires a value"):
        StepRun("missing", RequiredParameterStep(), {})
    assert StepRun(
        "supplied", RequiredParameterStep(), {}, parameters={"count": 21}
    ).parameters == {"count": 21}


def test_required_global_parameter_can_be_supplied_by_invocation():
    class RequiredGlobalStep(Step):
        name = "required-global"
        description = "Require a parameter with a global fallback."
        spec = StepSpec(params=[ScalarParam("count", int, config="shared.count")])

    with pytest.raises(ValueError, match="shared.count"):
        StepRun("missing", RequiredGlobalStep(), {})
    assert StepRun(
        "supplied", RequiredGlobalStep(), {}, parameters={"count": 21}
    ).parameters == {"count": 21}


def test_parameter_relationships_are_validated_for_invocations_and_config():
    with pytest.raises(ValueError, match="minimum must not exceed maximum"):
        StepRun("invalid", RangeStep(), {}, parameters={"minimum": 11})
    assert RangeStep().resolved_parameter_values({}) == {"minimum": 0, "maximum": 10}
    cfg.validate_step_config({"datadir": "."}, [RangeStep()])


def test_config_validation_reports_missing_invocation_only_parameter():
    with pytest.raises(ValueError, match="required-parameter.*count.*required"):
        cfg.validate_step_config({"datadir": "."}, [RequiredParameterStep()])


def test_run_reports_all_invalid_parameters():
    with pytest.raises(ValueError) as raised:
        StepRun(
            "invalid", ParameterStep(), {},
            parameters={"count": "bad", "local": True},
        )
    assert "parameter 'count'" in str(raised.value)
    assert "parameter 'local'" in str(raised.value)


def test_config_validation_collects_scalar_and_output_errors(tmp_path):
    class InvalidConfigurationStep(Step):
        name = "invalid-configuration"
        description = "Collect errors from independent configuration fields."
        result_output = FileOutput(
            "result",
            destination=OutputPathTemplate(
                "{sample}.txt", fields={"sample": TemplateField("shared.sample")}
            ),
        )
        spec = StepSpec(
            params=[ScalarParam("count", int, config="shared.count")],
            outputs=[result_output],
        )

    with pytest.raises(ValueError) as raised:
        cfg.validate_step_config(
            {"datadir": str(tmp_path), "shared": {"count": "bad"}},
            [InvalidConfigurationStep()],
        )
    assert "parameter 'count'" in str(raised.value)
    assert "shared.sample" in str(raised.value)


def test_parameter_relationship_validation_skips_invalid_scalars():
    class GlobalRangeStep(RangeStep):
        name = "global-parameter-range"
        spec = StepSpec(
            params=[
                ScalarParam("minimum", int, config="range.minimum", default=0),
                ScalarParam("maximum", int, default=10),
            ],
        )

    with pytest.raises(ValueError, match="parameter 'minimum'.*must be int"):
        StepRun("invalid", RangeStep(), {}, parameters={"minimum": "bad"})
    with pytest.raises(ValueError, match="parameter 'minimum'.*must be int"):
        cfg.validate_step_config(
            {"datadir": ".", "range": {"minimum": "bad"}}, [GlobalRangeStep()]
        )


def test_shared_fallback_rejects_conflicting_invocation_values(tmp_path):
    config = {"datadir": str(tmp_path), "shared": {"size": 10}}
    original = deepcopy(config)
    with pytest.raises(ValueError, match="first_size.*second_size.*conflicting.*shared.size"):
        StepRun(
            "invalid", SharedFallbackStep(), config,
            parameters={"first_size": 20},
        )
    assert config == original


def test_shared_fallback_accepts_agreeing_invocation_values(tmp_path):
    run = StepRun(
        "shared", SharedFallbackStep(), {"datadir": str(tmp_path)},
        parameters={"first_size": 20, "second_size": 20},
    )
    assert run.config["shared"]["size"] == 20
    assert run.output_paths()["result"] == tmp_path / "results/20.txt"


def test_config_validation_reports_conflicting_shared_defaults(tmp_path):
    class ConflictingDefaultsStep(Step):
        name = "conflicting-defaults"
        description = "Reject conflicting defaults at one configuration path."
        spec = StepSpec(
            params=[
                ScalarParam("first_size", int, config="shared.size", default=10),
                ScalarParam("second_size", int, config="shared.size", default=20),
            ],
        )

    with pytest.raises(ValueError, match="first_size.*second_size.*conflicting.*shared.size"):
        cfg.validate_step_config({"datadir": str(tmp_path)}, [ConflictingDefaultsStep()])


def test_cwl_wires_all_resolved_parameters_for_each_run(tmp_path):
    config = {"datadir": str(tmp_path)}
    first = StepRun("first", ParameterStep(), config)
    second = StepRun(
        "second",
        ParameterStep(),
        config,
        parameters={"mode": "slow", "local": 7, "label": None},
    )
    generated = generate_cwl_bundle([first, second])
    workflow = yaml.safe_load(generated.run_cwl)
    job = resolve_run_sequence_inputs([first, second], {})

    assert workflow["inputs"]["first.local"] == "int"
    assert workflow["steps"]["step_first"]["in"]["local"] == "first.local"
    assert workflow["steps"]["step_second"]["in"]["local"] == "second.local"
    assert job["first.local"] == 5
    assert job["second.local"] == 7
    assert job["second.label"] is None


def test_planner_resolves_parameters_without_global_paths(tmp_path):
    step = ParameterStep()
    plan = build_export_plan(
        [step], {"datadir": str(tmp_path)}, _registry={step.name: step}
    )
    assert plan.goals[0].parameters["local"] == 5


def test_receipt_uses_resolved_invocation_only_parameters(tmp_path):
    config = {"datadir": str(tmp_path)}
    first = StepRun("first", ParameterStep(), config, parameters={"local": 7})
    path = first.output_paths()["result"]
    path.parent.mkdir(parents=True)
    path.write_text("result")
    record_validated_outputs(first)
    same = StepRun("same", ParameterStep(), config, parameters={"local": 7})
    different = StepRun("different", ParameterStep(), config, parameters={"local": 8})

    assert reusable_output_paths(same) == first.output_paths()
    assert reusable_output_paths(different) is None


def _parse_cwl_command(run, tmp_path, inputs=None):
    pytest.importorskip("cwltool")
    from cwltool.context import LoadingContext, RuntimeContext
    from cwltool.load_tool import load_tool
    from cwltool.workflow import default_make_tool

    tool_path = tmp_path / "step.cwl"
    generated = StepCwlGenerator().render(run)
    tool_path.write_text(generated)
    tool = load_tool(
        str(tool_path), LoadingContext({"construct_tool_object": default_make_tool})
    )
    job = next(
        tool.job(
            to_cwl_inputs(resolve_run_inputs(run)) if inputs is None else inputs,
            lambda *args: None,
            RuntimeContext({"use_container": False, "outdir": str(tmp_path / "out")}),
        )
    )
    command = job.command_line
    base_command = yaml.safe_load(generated)["baseCommand"]
    return run.step.build_parser().parse_args(command[len(base_command) :])


@pytest.mark.parametrize(
    "label", [None, "custom", "fallback", ""]
)
def test_nullable_value_reaches_step_parser_through_cwl(tmp_path, label):
    run = StepRun(
        "clear", ParameterStep(), {"datadir": str(tmp_path)},
        parameters={"label": label},
    )
    args = _parse_cwl_command(run, tmp_path)
    assert {p.name: getattr(args, p.name) for p in run.step.spec.params} == run.parameters


@pytest.mark.parametrize(
    ("parameter", "value"),
    [
        (ScalarParam("value", str), "sample"),
        (ScalarParam("value", str | None), None),
        (ScalarParam("value", str | None), "sample"),
        (ScalarParam("value", str | None, default=None), "sample"),
        (ScalarParam("value", int | None, default=8), None),
        (ScalarParam("value", int | None, default=8), -8),
        (ScalarParam("value", float | None, default=1.5), None),
        (ScalarParam("value", float | None, default=1.5), -1.5),
        (ScalarParam("value", Literal["fast", "slow"] | None, default="fast"), None),
        (ScalarParam("value", Literal["fast", "slow"] | None, default="fast"), "slow"),
    ],
)
def test_scalar_bindings_preserve_types_and_values(tmp_path, parameter, value):
    class ScalarStep(Step):
        name = "scalar-binding"
        description = "Pass one scalar through CWL."
        spec = StepSpec(params=[parameter, ScalarParam("enabled", bool)])

    run = StepRun("scalar", ScalarStep(), {}, parameters={"value": value})
    args = _parse_cwl_command(run, tmp_path)
    assert args.value == value
    assert args.enabled is False


def test_cwl_non_null_value_overrides_the_default_clearing_argument(tmp_path):
    run = StepRun(
        "clear", ParameterStep(), {"datadir": str(tmp_path)},
        parameters={"label": None},
    )
    inputs = to_cwl_inputs(resolve_run_inputs(run))
    inputs["label"] = "custom"
    args = _parse_cwl_command(run, tmp_path, inputs)
    assert args.label == "custom"
    assert args.enabled is False


@pytest.mark.parametrize(
    ("first", "second"),
    [(None, None), (None, "custom"), ("custom", None)],
)
def test_multiple_nullable_bindings_preserve_each_value(tmp_path, first, second):
    class NullableStep(Step):
        name = "nullable-bindings"
        description = "Clear nullable defaults independently."
        spec = StepSpec(params=[
            ScalarParam("first", str | None, default="one"),
            ScalarParam("second", str | None, default="two"),
            ScalarParam("enabled", bool),
        ])

    run = StepRun(
        "nullable", NullableStep(), {},
        parameters={"first": first, "second": second},
    )
    args = _parse_cwl_command(run, tmp_path)
    assert args.first == first
    assert args.second == second
    assert args.enabled is False


def test_cwl_defaults_use_resolved_invocation_values(tmp_path):
    run = StepRun(
        "defaults", ParameterStep(), {"datadir": str(tmp_path)},
        parameters={
            "mode": "slow", "count": 0, "enabled": True, "label": None, "local": 7,
        },
    )
    args = _parse_cwl_command(run, tmp_path, inputs={})
    assert {p.name: getattr(args, p.name) for p in run.step.spec.params} == run.parameters


class SchemaParameterStep(Step):
    name = "schema-parameter"
    description = "Validate resolved values against a configuration field."
    spec = StepSpec(
        params=[ScalarParam("count", int, config="parameters.target.k", default=1)],
    )


@pytest.mark.parametrize("count", [0, -1])
def test_schema_constraints_apply_to_shared_values_and_run_overrides(count):
    step = SchemaParameterStep()
    with pytest.raises(ValueError, match="parameters.target.k"):
        step.resolved_parameter_values({"parameters": {"target": {"k": count}}})
    with pytest.raises(ValueError, match="parameters.target.k"):
        StepRun("invalid", step, {}, parameters={"count": count})


def test_schema_validation_checks_the_resolved_override():
    assert SchemaParameterStep().resolved_parameter_values(
        {"parameters": {"target": {"k": 0}}}, {"count": 4}
    ) == {"count": 4}


def test_schema_constraints_apply_to_declared_defaults():
    class InvalidDefaultStep(Step):
        name = "invalid-schema-default"
        description = "Reject a default that violates its config schema."
        spec = StepSpec(
            params=[ScalarParam("count", int, config="parameters.target.k", default=0)],
        )

    with pytest.raises(ValueError, match="parameters.target.k"):
        InvalidDefaultStep().resolved_parameter_values({})


def test_plugin_schema_constraints_apply_to_resolved_values(tmp_path, monkeypatch):
    schema_path = tmp_path / "config.schema.yaml"
    schema_path.write_text(
        "type: object\n"
        "$defs:\n"
        "  count: {type: integer, minimum: 3}\n"
        "properties:\n"
        "  shared:\n"
        "    type: object\n"
        "    properties:\n"
        "      count: {$ref: '#/$defs/count'}\n"
    )
    monkeypatch.setattr(
        "ASOkai._pipeline.catalog.get_config_schema_paths",
        lambda: {"example": schema_path},
    )
    with pytest.raises(ValueError, match="example.*shared.count"):
        ParameterStep().resolved_parameter_values({}, {"count": 2})
    assert ParameterStep().resolved_parameter_values({}, {"count": 3})["count"] == 3
