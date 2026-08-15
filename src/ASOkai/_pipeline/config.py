#!/usr/bin/env python
"""
Filename: src/ASOkai/_pipeline/config.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Version: 0.1.1
Description: Config loading and resolution utilities.
License: LGPL-3.0-or-later
"""
from __future__ import annotations

from copy import deepcopy
from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping, Sequence

import yaml
from jsonschema.exceptions import SchemaError

from ASOkai._cwl.model import _UNSET
from ASOkai._pipeline.contracts.json_schema import (
    JsonSchema,
    json_schema_errors,
)
from ASOkai._pipeline.contracts.parameters import ScalarParam

if TYPE_CHECKING:
    from ASOkai._pipeline.steps.base import Step


RESOURCE_N_PROCESSES_KEY = "n_processes"
RESOURCE_MEMORY_KEY = "memory_mb"
RESOURCE_DEFAULT_KEY = "default"
DEFAULT_STEP_RESOURCES = {
    RESOURCE_N_PROCESSES_KEY: 1,
    RESOURCE_MEMORY_KEY: 4096,
}
_CONFIG_SCHEMA_PATH = Path(__file__).with_name("config.schema.yaml")


def load(path: Path | str) -> dict:
    """Load a YAML configuration whose root is a mapping."""
    source = Path(path)
    try:
        data = yaml.safe_load(source.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        raise ValueError(
            f"Invalid YAML configuration in {source}: {error}"
        ) from error
    if not isinstance(data, Mapping):
        raise ValueError(
            f"Configuration in {source} must contain a mapping at its root."
        )
    config = dict(data)
    validate_config_schema(config)
    return config


def resolve(config: Mapping[str, Any], dotted_key: str) -> Any:
    """
    Resolve a dotted key against a config dict.

    Example:
        resolve(config, "genome.assembly_id")  →  config["genome"]["assembly_id"]
    """
    keys = _dotted_key_parts(dotted_key)
    value: Any = config
    traversed: list[str] = []
    for key in keys:
        if not isinstance(value, Mapping):
            parent = ".".join(traversed) or "<root>"
            raise KeyError(
                f"Config key '{dotted_key}' cannot be resolved because "
                f"'{parent}' is not a mapping."
            )
        if key not in value:
            raise KeyError(
                f"Config key '{dotted_key}' not found (missing '{key}')."
            )
        value = value[key]
        traversed.append(key)
    return value


def apply_overrides(config: dict, overrides: dict[str, Any]) -> dict:
    """
    Apply CLI overrides to config in-place.

    Overrides use dotted keys, e.g.:
        {"genome.ensembl_release": 115}  →  config["genome"]["ensembl_release"] = 115
    """
    for dotted_key, value in overrides.items():
        keys = _dotted_key_parts(dotted_key)
        target = config
        for key in keys[:-1]:
            existing = target.get(key)
            if existing is None:
                nested: dict[str, Any] = {}
                target[key] = nested
                target = nested
                continue
            if not isinstance(existing, dict):
                raise ValueError(
                    f"Config override '{dotted_key}' cannot descend through "
                    f"non-mapping key '{key}'."
                )
            target = existing
        target[keys[-1]] = value
    return config


def resolve_parameter_value(
    config: Mapping[str, Any],
    parameter: ScalarParam,
) -> Any:
    """Resolve one configured parameter, including its declared fallback."""
    if parameter.config is None:
        raise ValueError(
            f"Parameter '{parameter.name}' does not declare a config path."
        )
    try:
        return resolve(config, parameter.config)
    except KeyError:
        if parameter.default is not _UNSET:
            return deepcopy(parameter.default)
        if not parameter.parser_required():
            return None
        raise


def validate_step_config(
    config: Any,
    steps: Sequence[Step],
) -> None:
    """Validate selected-step values, compatibility, paths, and input files."""
    errors: list[str] = []
    datadir = Path(config["datadir"])
    if datadir.exists() and not datadir.is_dir():
        errors.append(f"$.datadir: {datadir} is not a directory")

    for step in _unique_steps(steps):
        missing_parameter = False
        parameters_are_valid = True
        parameter_values: dict[str, object] = {}
        parameters_by_path = {
            parameter.config: parameter
            for parameter in step.spec.params
            if parameter.config is not None
        }
        for parameter in step.spec.params:
            if parameter.config is None:
                continue
            try:
                configured_value = resolve_parameter_value(config, parameter)
            except KeyError:
                errors.append(
                    f"$.{parameter.config}: required by step "
                    f"'{step.name}'"
                )
                missing_parameter = True
                parameters_are_valid = False
                continue

            parameter_values[parameter.name] = configured_value

            accepted_values = parameter.parser_choices()
            if accepted_values is None or any(
                type(configured_value) is type(accepted_value)
                and configured_value == accepted_value
                for accepted_value in accepted_values
            ):
                continue
            accepted = ", ".join(repr(value) for value in accepted_values)
            errors.append(
                f"$.{parameter.config}: configured value "
                f"{configured_value!r} is not accepted by step "
                f"'{step.name}'; accepted values: {accepted}"
            )
            parameters_are_valid = False

        if parameters_are_valid:
            try:
                step.validate_parameters(parameter_values)
            except ValueError as error:
                errors.append(f"Step '{step.name}' parameters: {error}")

        for path, supported_values in step.spec.compatible_with.items():
            parameter = parameters_by_path.get(path)
            try:
                configured_value = (
                    resolve_parameter_value(config, parameter)
                    if parameter is not None
                    else resolve(config, path)
                )
            except KeyError:
                if parameter is None:
                    errors.append(
                        f"$.{path}: required to determine whether step "
                        f"'{step.name}' is compatible"
                    )
                continue

            is_supported = any(
                type(configured_value) is type(supported_value)
                and configured_value == supported_value
                for supported_value in supported_values
            )
            if not is_supported:
                supported = ", ".join(
                    repr(value) for value in supported_values
                )
                errors.append(
                    f"$.{path}: configured value {configured_value!r} is "
                    f"incompatible with step '{step.name}'; supported "
                    f"values: {supported}"
                )

        for file_input in step.spec.inputs:
            try:
                override_path = file_input.configured_override_path(config)
            except (KeyError, TypeError, ValueError) as error:
                errors.append(str(error))
                continue
            if override_path is None:
                continue
            if not override_path.exists():
                errors.append(
                    f"$.{file_input.override}: file does not exist: "
                    f"{override_path}"
                )
                continue
            if not override_path.is_file():
                errors.append(
                    f"$.{file_input.override}: path is not a file: "
                    f"{override_path}"
                )
                continue
            try:
                file_input.read(override_path)
            except (
                OSError,
                UnicodeError,
                TypeError,
                ValueError,
            ) as error:
                errors.append(f"$.{file_input.override}: {error}")

        if not missing_parameter:
            for output in step.spec.outputs:
                try:
                    step.output_relative_path(output.name, config)
                except (KeyError, TypeError, ValueError) as error:
                    errors.append(
                        f"Step '{step.name}' output '{output.name}': {error}"
                    )

    if errors:
        _raise_config_errors(errors)


def validate_step_config_paths(
    steps: Sequence[Step],
    plugin_schema_paths: Mapping[str, Path] | None = None,
) -> None:
    """Require every step config path to exist in a registered schema."""
    schemas = {"ASOkai": _load_config_schema()}
    for plugin_name, schema_path in (plugin_schema_paths or {}).items():
        owner = f"Plugin '{plugin_name}'"
        schema = _read_config_schema(schema_path, owner)
        schemas[owner] = schema

    errors: list[str] = []
    for step in _unique_steps(steps):
        paths = [
            parameter.config
            for parameter in step.spec.params
            if parameter.config is not None
        ]
        paths.extend(
            file_input.override
            for file_input in step.spec.inputs
            if file_input.override is not None
        )
        paths.extend(step.spec.compatible_with)
        for path in dict.fromkeys(paths):
            if any(
                _schema_declares_path(schema, path)
                for schema in schemas.values()
            ):
                continue
            errors.append(
                f"Step '{step.name}' uses '{path}', but no registered "
                "configuration schema declares it."
            )

    if errors:
        details = "\n".join(f"- {error}" for error in errors)
        raise ValueError(f"Invalid step configuration contract:\n{details}")


def validate_config_schema(
    config: Any,
) -> None:
    """Validate data against ASOkai and installed-plugin config schemas."""
    errors = _schema_errors("ASOkai", _load_config_schema(), config)

    from ASOkai.Plugins._registry import get_config_schema_paths

    for plugin_name, schema_path in get_config_schema_paths().items():
        schema = _read_config_schema(
            schema_path,
            f"plugin '{plugin_name}'",
        )
        errors.extend(
            _schema_errors(
                f"Plugin '{plugin_name}'",
                schema,
                config,
            )
        )

    if errors:
        _raise_config_errors(errors)

@cache
def _load_config_schema() -> JsonSchema:
    """Load ASOkai's checked-in configuration schema once."""
    return _read_config_schema(_CONFIG_SCHEMA_PATH, "ASOkai")


def _read_config_schema(
    path: Path,
    owner: str,
) -> JsonSchema:
    """Read one YAML configuration schema."""
    try:
        schema = yaml.safe_load(
            path.read_text(encoding="utf-8")
        )
    except (OSError, yaml.YAMLError) as error:
        raise ValueError(
            f"Could not load {owner} configuration schema at "
            f"{path}: {error}"
        ) from error
    if not isinstance(schema, Mapping):
        raise ValueError(
            f"{owner} configuration schema at {path} "
            "must contain a mapping at its root."
        )
    return dict(schema)


def _schema_errors(
    owner: str,
    schema: JsonSchema,
    config: Any,
) -> list[str]:
    """Return readable errors from one configuration schema."""
    try:
        errors = json_schema_errors(schema, config)
    except SchemaError as error:
        raise ValueError(
            f"{owner} configuration schema is invalid: {error.message}"
        ) from error
    if owner == "ASOkai":
        return errors
    return [f"{owner} schema: {error}" for error in errors]


def _schema_declares_path(
    schema: Mapping[str, Any],
    dotted_path: str,
) -> bool:
    """Return whether nested schema properties declare a dotted path."""
    current: Any = schema
    for name in _dotted_key_parts(dotted_path):
        properties = (
            current.get("properties")
            if isinstance(current, Mapping)
            else None
        )
        if not isinstance(properties, Mapping) or name not in properties:
            return False
        current = properties[name]
    return True


def _dotted_key_parts(dotted_key: str) -> tuple[str, ...]:
    """Return validated components of a dotted configuration key."""
    if type(dotted_key) is not str:
        raise TypeError("Config keys must be strings.")
    parts = tuple(dotted_key.split("."))
    if not parts or any(not part.strip() for part in parts):
        raise ValueError(
            f"Invalid dotted config key: {dotted_key!r}."
        )
    return parts


def _unique_steps(steps: Sequence[Step]) -> list[Step]:
    """Return steps deduplicated by name while preserving their order."""
    unique: dict[str, Step] = {}
    for step in steps:
        unique.setdefault(step.name, step)
    return list(unique.values())


def _raise_config_errors(errors: Sequence[str]) -> None:
    """Raise one readable error containing every configuration issue."""
    details = "\n".join(f"- {error}" for error in errors)
    raise ValueError(f"Invalid configuration:\n{details}")


def step_resources(config: Mapping[str, Any], step_name: str) -> dict[str, Any]:
    """Return resolved resource settings for one step."""
    return {
        **DEFAULT_STEP_RESOURCES,
        **step_resource_overrides(config, step_name),
    }


def step_resource_overrides(
    config: Mapping[str, Any],
    step_name: str,
) -> dict[str, Any]:
    """Return configured values for one step without built-in defaults."""
    all_resources = config.get("resources", {})
    configured_defaults = all_resources.get(RESOURCE_DEFAULT_KEY, {})
    step_overrides = all_resources.get(step_name, {})
    return {**configured_defaults, **step_overrides}
