#!/usr/bin/env python
"""
Filename: src/ASOkai/_pipeline/contracts/paths.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Structured output-path templates for pipeline files.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import PurePosixPath, PureWindowsPath
from string import Formatter
from typing import Any, Mapping


@dataclass(frozen=True)
class TemplateField:
    """A structured template value read from configuration."""

    config_path: str
    fallbacks: tuple[str, ...] = ()
    default: str | int | float | bool | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "fallbacks", tuple(self.fallbacks))
        for config_path in self.config_paths():
            if (
                type(config_path) is not str
                or not config_path.strip()
                or any(not part.strip() for part in config_path.split("."))
            ):
                raise ValueError(
                    "TemplateField configuration paths must be non-blank "
                    "dotted paths."
                )
        if self.default is not None and (
            type(self.default) not in (str, int, float, bool)
            or self.default == ""
        ):
            raise TypeError(
                "TemplateField.default must be a non-empty scalar value."
            )

    @classmethod
    def first_of(
        cls,
        *config_paths: str,
    ) -> TemplateField:
        """Return a field that uses the first non-empty configured value."""
        if not config_paths:
            raise ValueError(
                "TemplateField.first_of requires at least one config path."
            )
        return cls(config_paths[0], tuple(config_paths[1:]))

    def config_paths(self) -> tuple[str, ...]:
        """Return every configuration path this field may read."""
        return (self.config_path, *self.fallbacks)

    def resolve(self, config: Mapping[str, Any]) -> str | int | float | bool:
        """Resolve one scalar field from validated configuration."""
        from ASOkai._pipeline.config import resolve

        value = None
        for config_path in self.config_paths():
            try:
                candidate = resolve(config, config_path)
            except KeyError:
                continue
            if candidate is not None and candidate != "":
                value = candidate
                break
        if value is None:
            value = self.default
        if value is None:
            names = ", ".join(self.config_paths())
            raise ValueError(
                "No value is available for template configuration path(s): "
                f"{names}."
            )
        if type(value) not in (str, int, float, bool):
            names = ", ".join(self.config_paths())
            raise TypeError(
                "Output path configuration value must be scalar for path(s): "
                f"{names}."
            )
        return value


@dataclass(frozen=True)
class InputConfigField:
    """A template value read from one file input's resolved configuration."""

    input_name: str
    config_path: str

    def __post_init__(self) -> None:
        if type(self.input_name) is not str or not self.input_name.strip():
            raise ValueError("InputConfigField.input_name must be non-blank.")
        TemplateField(self.config_path)

    def config_paths(self) -> tuple[str, ...]:
        """Return the configuration path read from this input."""
        return (self.config_path,)

    def resolve(
        self,
        input_configurations: Mapping[str, Mapping[str, Any]],
    ) -> str | int | float | bool:
        """Resolve the field from the selected input's configuration."""
        try:
            input_config = input_configurations[self.input_name]
        except KeyError as error:
            raise ValueError(
                f"No resolved configuration is available for file input "
                f"'{self.input_name}'."
            ) from error
        if not isinstance(input_config, Mapping):
            raise TypeError(
                f"Resolved configuration for file input '{self.input_name}' "
                "must be a mapping."
            )
        return TemplateField(self.config_path).resolve(input_config)


@dataclass(frozen=True)
class OutputPathTemplate:
    """A structured template for an output path relative to ``datadir``."""

    template: str
    fields: Mapping[str, TemplateField | InputConfigField] = field(
        default_factory=dict
    )

    def __post_init__(self) -> None:
        declared_fields = dict(self.fields)
        parsed_fields: list[str] = []
        for _, field_name, format_spec, conversion in Formatter().parse(
            self.template
        ):
            if field_name is None:
                continue
            if not field_name or "." in field_name or "[" in field_name:
                raise ValueError(
                    f"Output path field must be a simple input name: "
                    f"{field_name!r}."
                )
            if format_spec or conversion:
                raise ValueError(
                    "Output path templates do not support format specs or "
                    "conversions."
                )
            parsed_fields.append(field_name)

        unknown_fields = set(declared_fields) - set(parsed_fields)
        if unknown_fields:
            names = ", ".join(sorted(unknown_fields))
            raise ValueError(
                f"Output path field rule(s) are not used by the template: "
                f"{names}."
            )

        invalid_fields = {
            name
            for name, value in declared_fields.items()
            if not isinstance(value, (TemplateField, InputConfigField))
        }
        if invalid_fields:
            names = ", ".join(sorted(invalid_fields))
            raise TypeError(
                "Output path fields must be TemplateField or InputConfigField "
                f"values: {names}."
            )

        for field_name in parsed_fields:
            declared_fields.setdefault(field_name, TemplateField(field_name))
        object.__setattr__(self, "fields", declared_fields)

    def config_paths(self) -> set[str]:
        """Return every configuration path referenced by this destination."""
        return {
            config_path
            for template_field in self.fields.values()
            for config_path in template_field.config_paths()
        }

    def input_names(self) -> set[str]:
        """Return every concrete file input referenced by this destination."""
        return {
            template_field.input_name
            for template_field in self.fields.values()
            if isinstance(template_field, InputConfigField)
        }

    def validate_configuration(self, config: Mapping[str, Any]) -> None:
        """Validate template fields against the main configuration."""
        for template_field in self.fields.values():
            if isinstance(template_field, TemplateField):
                template_field.resolve(config)
            else:
                TemplateField(template_field.config_path).resolve(config)

    def render(
        self,
        config: Mapping[str, Any],
        input_configurations: Mapping[
            str,
            Mapping[str, Any],
        ] | None = None,
    ) -> PurePosixPath:
        """Render and validate the relative output path."""
        input_configurations = input_configurations or {}
        rendered: list[str] = []
        for literal, field_name, _, _ in Formatter().parse(self.template):
            rendered.append(literal)
            if field_name is not None:
                template_field = self.fields[field_name]
                if isinstance(template_field, InputConfigField):
                    value = template_field.resolve(input_configurations)
                else:
                    value = template_field.resolve(config)
                rendered.append(str(value))
        rendered_path = "".join(rendered)
        path = PurePosixPath(rendered_path)
        windows_path = PureWindowsPath(rendered_path)
        if (
            path.is_absolute()
            or not path.parts
            or ".." in path.parts
            or "\\" in rendered_path
            or bool(windows_path.drive)
        ):
            raise ValueError(f"Output path must stay below datadir: {path!s}.")
        return path
