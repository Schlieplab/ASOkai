#!/usr/bin/env python
"""
Filename: src/ASOkai/_pipeline/config.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Config loading and resolution utilities.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

from copy import deepcopy
from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING, AbstractSet, Any, Literal, Mapping, Sequence

import yaml
from jsonschema.exceptions import SchemaError
from jsonschema.validators import validator_for

from ASOkai._cwl.model import _UNSET
from ASOkai._pipeline.contracts.json_schema import (
    JsonSchema,
    json_schema_errors,
)
from ASOkai._pipeline.contracts.parameters import ScalarParam

if TYPE_CHECKING:
    from ASOkai._pipeline.contracts.files import FileInput
    from ASOkai._pipeline.steps.base import Step


RESOURCE_N_THREADS_KEY = "n_threads"
RESOURCE_MEMORY_KEY = "memory_mb"
RESOURCE_DEFAULT_KEY = "default"
DEFAULT_STEP_RESOURCES = {
    RESOURCE_N_THREADS_KEY: 1,
    RESOURCE_MEMORY_KEY: 4096,
}
_CONFIG_SCHEMA_PATH = Path(__file__).with_name("config.schema.yaml")
OutputValidationMode = Literal["signature", "contract"]


def output_validation_mode(config: Mapping[str, Any]) -> OutputValidationMode:
    """Return how existing generated outputs are checked for reuse."""
    validation = config.get("validation")
    if not isinstance(validation, Mapping):
        return "signature"
    return (
        "contract" if validation.get("existing_outputs") == "contract" else "signature"
    )


def load(
    path: Path | str,
) -> dict:
    """Read a YAML configuration mapping without validating its values."""
    source = Path(path)
    try:
        data = yaml.safe_load(source.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        raise ValueError(f"Invalid YAML configuration in {source}: {error}") from error
    if not isinstance(data, Mapping):
        raise ValueError(
            f"Configuration in {source} must contain a mapping at its root."
        )
    return dict(data)


def resolve(config: Mapping[str, Any], dotted_key: str) -> Any:
    """
    Resolve a dotted key against a config dict.

    Example:
        resolve(config, "parameters.genome.assembly")
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
            raise KeyError(f"Config key '{dotted_key}' not found (missing '{key}').")
        value = value[key]
        traversed.append(key)
    return value


def apply_overrides(config: dict, overrides: dict[str, Any]) -> dict:
    """
    Apply dotted-key overrides to config in-place.

    Overrides use dotted keys, e.g.:
        {"parameters.genome.release": 115} updates that shared value.
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
    *,
    override: Any = _UNSET,
) -> Any:
    """Resolve invocation values, global configuration, then declared defaults."""
    if override is not _UNSET:
        return override
    if parameter.config is not None:
        try:
            return resolve(config, parameter.config)
        except KeyError:
            if parameter.parser_required():
                raise
    if parameter.default is not _UNSET:
        return deepcopy(parameter.default)
    if not parameter.parser_required():
        return None
    raise KeyError(f"Parameter '{parameter.name}' requires a value.")


def _resolve_step_parameters(
    config: Mapping[str, Any],
    step: Step,
    parameters: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """Resolve one parameter set and collect scalar and relationship errors."""
    if parameters is not None:
        if not isinstance(parameters, Mapping):
            raise TypeError("Invocation parameters must be a mapping.")
        unknown = set(parameters) - {parameter.name for parameter in step.spec.params}
        if unknown:
            names = ", ".join(sorted(str(name) for name in unknown))
            raise ValueError(f"Step '{step.name}' has unknown parameter(s): {names}.")

    values: dict[str, Any] = {}
    errors: list[str] = []
    for parameter in step.spec.params:
        location = (
            f"$.{parameter.config}"
            if parameter.config is not None
            else f"Step '{step.name}' parameter '{parameter.name}'"
        )
        override = (
            parameters.get(parameter.name, _UNSET) if parameters is not None else _UNSET
        )
        try:
            value = resolve_parameter_value(config, parameter, override=override)
        except KeyError:
            errors.append(
                f"{location}: parameter '{parameter.name}' requires a value "
                f"(required by step '{step.name}')"
            )
            continue
        values[parameter.name] = value
        try:
            parameter.validate(value)
        except (TypeError, ValueError) as error:
            errors.append(f"{location}: {error}")

    if not errors:
        try:
            step.validate_parameters(values)
        except ValueError as error:
            errors.append(f"Step '{step.name}' parameters: {error}")
    return values, errors


def validate_step_config(
    config: Any,
    steps: Sequence[Step],
    *,
    validate_input_files: bool = True,
    parameters: Mapping[str, Any] | None = None,
    skip_input_names: AbstractSet[str] = frozenset(),
    input_configurations: Mapping[str, Mapping[str, Any]] | None = None,
) -> None:
    """Validate selected-step values, compatibility, paths, and input files."""
    errors: list[str] = []
    datadir = Path(config["datadir"])
    if datadir.exists() and not datadir.is_dir():
        errors.append(f"$.datadir: {datadir} is not a directory")

    for step in _unique_steps(steps):
        parameter_values, parameter_errors = _resolve_step_parameters(
            config, step, parameters
        )
        errors.extend(parameter_errors)
        configured_step_resources = config.get("resources", {}).get(
            step.name,
            {},
        )
        if isinstance(configured_step_resources, Mapping):
            supported_resources = set(step_resource_names(step))
            for resource_name in configured_step_resources:
                if resource_name not in supported_resources:
                    errors.append(
                        f"$.resources.{step.name}.{resource_name}: step "
                        f"'{step.name}' does not support this resource setting"
                    )
        try:
            step.validate_resources(step_resources(config, step))
        except ValueError as error:
            errors.append(f"$.resources.{step.name}: {error}")
        parameters_by_path = {
            parameter.config: parameter
            for parameter in step.spec.params
            if parameter.config is not None
        }
        for path, supported_values in step.spec.compatible_with.items():
            parameter = parameters_by_path.get(path)
            try:
                configured_value = (
                    parameter_values[parameter.name]
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
                supported = ", ".join(repr(value) for value in supported_values)
                errors.append(
                    f"$.{path}: configured value {configured_value!r} is "
                    f"incompatible with step '{step.name}'; supported "
                    f"values: {supported}"
                )

        for file_input in step.spec.inputs:
            if file_input.name in skip_input_names:
                continue
            configuration_path = file_input.configuration_path(step.name)
            try:
                path_override = file_input.configured_path_override(
                    config,
                    step.name,
                )
            except (TypeError, ValueError) as error:
                errors.append(f"$.{configuration_path}: {error}")
                continue
            if path_override is not None:
                if not validate_input_files:
                    continue
                path_config = f"{configuration_path}.path_override"
                try:
                    validate_file_input_path(
                        file_input, path_override, f"$.{path_config}"
                    )
                except (
                    OSError,
                    UnicodeError,
                    TypeError,
                    ValueError,
                ) as error:
                    errors.append(str(error))

        if len(parameter_values) == len(step.spec.params):
            try:
                output_config = step._configuration_for_parameters(
                    config, parameter_values
                )
            except (TypeError, ValueError) as error:
                errors.append(f"Step '{step.name}' configuration: {error}")
                continue
            for output in step.spec.outputs:
                try:
                    output.destination.validate_configuration(
                        output_config, input_configurations
                    )
                except (KeyError, TypeError, ValueError) as error:
                    errors.append(f"Step '{step.name}' output '{output.name}': {error}")

    if errors:
        _raise_config_errors(errors)


def validate_file_input_path(
    file_input: FileInput,
    path: Path,
    location: str,
) -> None:
    """Validate an external path using the input's artifact contract."""
    if not path.exists():
        raise ValueError(f"{location}: file does not exist: {path}")
    is_directory = file_input.file_type.cwl_type == "Directory"
    if is_directory and not path.is_dir():
        raise ValueError(f"{location}: path is not a directory: {path}")
    if not is_directory and not path.is_file():
        raise ValueError(f"{location}: path is not a file: {path}")
    try:
        file_input.validate(path)
    except (OSError, UnicodeError, TypeError, ValueError) as error:
        raise ValueError(f"{location}: {error}") from error


def validate_configured_step_names(
    config: Mapping[str, Any],
    registered_steps: Mapping[str, Step],
) -> None:
    """Validate dynamic step, input, and resource names against the registry."""
    errors: list[str] = []
    configured_steps = config.get("steps", {})
    configured_resources = config.get("resources", {})

    for step_name, step_config in configured_steps.items():
        step = registered_steps.get(step_name)
        if step is None:
            errors.append(f"$.steps.{step_name}: unknown step")
            continue

        declared_inputs = {file_input.name for file_input in step.spec.inputs}
        for input_name in step_config.get("inputs", {}):
            if input_name not in declared_inputs:
                errors.append(
                    f"$.steps.{step_name}.inputs.{input_name}: step "
                    f"'{step_name}' has no input with this name"
                )

    for step_name in configured_resources:
        if step_name != RESOURCE_DEFAULT_KEY and step_name not in registered_steps:
            errors.append(f"$.resources.{step_name}: unknown step")

    if errors:
        _raise_config_errors(errors)


def _registered_config_schemas(
    plugin_schema_paths: Mapping[str, Path] | None = None,
) -> dict[str, JsonSchema]:
    """Load the built-in and installed configuration contracts."""
    schemas = {"ASOkai": _load_config_schema()}
    for plugin_name, schema_path in (plugin_schema_paths or {}).items():
        owner = f"Plugin '{plugin_name}'"
        schema = load_config_schema(schema_path, owner)
        schemas[owner] = schema
    return schemas


def validate_step_config_paths(
    steps: Sequence[Step],
    plugin_schema_paths: Mapping[str, Path] | None = None,
) -> None:
    """Require every step config path to exist in a registered schema."""
    schemas = _registered_config_schemas(plugin_schema_paths)

    errors: list[str] = []
    for step in _unique_steps(steps):
        paths = [
            parameter.config
            for parameter in step.spec.params
            if parameter.config is not None
        ]
        for output in step.spec.outputs:
            paths.extend(output.destination.config_paths())
        paths.extend(step.spec.compatible_with)
        for path in dict.fromkeys(paths):
            if any(_schema_declares_path(schema, path) for schema in schemas.values()):
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
    *,
    plugin_schema_paths: Mapping[str, Path] | None = None,
) -> None:
    """Validate data against ASOkai and installed-plugin config schemas."""
    if isinstance(config, Mapping):
        old_groups = {"genome", "target", "antisense"} & config.keys()
        if old_groups:
            _raise_config_errors(
                [
                    f"$.{name}: move this group under parameters.{name}"
                    for name in sorted(old_groups)
                ]
            )
    resources = config.get("resources") if isinstance(config, Mapping) else None
    if isinstance(resources, Mapping):
        migration_errors = [
            f"$.resources.{name}.n_processes: renamed to n_threads; "
            f"use resources.{name}.n_threads instead"
            for name, values in resources.items()
            if isinstance(values, Mapping) and "n_processes" in values
        ]
        if migration_errors:
            _raise_config_errors(migration_errors)

    errors = _schema_errors("ASOkai", _load_config_schema(), config)

    if plugin_schema_paths is None:
        from ASOkai._pipeline.catalog import get_config_schema_paths

        plugin_schema_paths = get_config_schema_paths()

    for plugin_name, schema_path in plugin_schema_paths.items():
        schema = load_config_schema(
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
    return load_config_schema(_CONFIG_SCHEMA_PATH, "ASOkai")


def load_config_schema(
    path: Path,
    owner: str,
) -> JsonSchema:
    """Read and validate one YAML configuration schema."""
    try:
        schema = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise ValueError(
            f"Could not load {owner} configuration schema at " f"{path}: {error}"
        ) from error
    if not isinstance(schema, Mapping):
        raise ValueError(
            f"{owner} configuration schema at {path} "
            "must contain a mapping at its root."
        )
    loaded = dict(schema)
    try:
        validator_for(loaded).check_schema(loaded)
    except SchemaError as error:
        raise ValueError(
            f"{owner} configuration schema is invalid: {error.message}"
        ) from error
    return loaded


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
        properties = current.get("properties") if isinstance(current, Mapping) else None
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
        raise ValueError(f"Invalid dotted config key: {dotted_key!r}.")
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


def step_resource_names(step: Step) -> tuple[str, ...]:
    """Return resource settings that may be configured for a step."""
    return tuple(
        resource_name
        for resource_name in DEFAULT_STEP_RESOURCES
        if (resource_name != RESOURCE_N_THREADS_KEY or step.supports_multiple_threads)
    )


def step_resources(config: Mapping[str, Any], step: Step) -> dict[str, Any]:
    """Return resolved resource settings for one step."""
    configured = step_resource_overrides(config, step.name)
    return {
        resource_name: configured.get(
            resource_name,
            DEFAULT_STEP_RESOURCES[resource_name],
        )
        for resource_name in step_resource_names(step)
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
