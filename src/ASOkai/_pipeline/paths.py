#!/usr/bin/env python
"""
Filename: src/ASOkai/_pipeline/paths.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Version: 0.1.1
Description: Structured output-path templates for pipeline files.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import PurePosixPath
from string import Formatter
from typing import Any, Literal, Mapping


TemplateTransform = Literal["identity", "species_case"]


@dataclass(frozen=True)
class TemplateField:
    """A structured template value read from one or more step parameters."""

    input_name: str
    fallbacks: tuple[str, ...] = ()
    transform: TemplateTransform = "identity"

    def __post_init__(self) -> None:
        object.__setattr__(self, "fallbacks", tuple(self.fallbacks))
        if self.transform not in ("identity", "species_case"):
            raise ValueError(f"Unknown template transform: {self.transform!r}.")

    @classmethod
    def first_of(
        cls,
        *input_names: str,
        transform: TemplateTransform = "identity",
    ) -> TemplateField:
        """Return a field that uses the first non-empty input value."""
        if not input_names:
            raise ValueError(
                "TemplateField.first_of requires at least one input name."
            )
        return cls(input_names[0], tuple(input_names[1:]), transform)

    def input_names(self) -> tuple[str, ...]:
        """Return every CWL input this field may read."""
        return (self.input_name, *self.fallbacks)

    def resolve(self, values: Mapping[str, Any]) -> Any:
        """Resolve and transform this field from Python input values."""
        value = None
        for input_name in self.input_names():
            candidate = values.get(input_name)
            if candidate is not None and candidate != "":
                value = candidate
                break
        if value is None:
            names = ", ".join(self.input_names())
            raise ValueError(
                f"No value is available for template input(s): {names}."
            )
        if self.transform == "species_case":
            parts = str(value).split("_")
            return "_".join(
                part.capitalize() if index == 0 else part.lower()
                for index, part in enumerate(parts)
            )
        return value


@dataclass(frozen=True)
class OutputPathTemplate:
    """A structured template for an output path relative to ``datadir``."""

    template: str
    fields: Mapping[str, TemplateField] = field(default_factory=dict)

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

        for field_name in parsed_fields:
            declared_fields.setdefault(field_name, TemplateField(field_name))
        object.__setattr__(self, "fields", declared_fields)

    def input_names(self) -> set[str]:
        """Return every CWL input referenced by this filename."""
        return {
            input_name
            for template_field in self.fields.values()
            for input_name in template_field.input_names()
        }

    def render(self, values: Mapping[str, Any]) -> PurePosixPath:
        """Render and validate the relative output path."""
        rendered: list[str] = []
        for literal, field_name, _, _ in Formatter().parse(self.template):
            rendered.append(literal)
            if field_name is not None:
                rendered.append(str(self.fields[field_name].resolve(values)))
        path = PurePosixPath("".join(rendered))
        if path.is_absolute() or not path.parts or ".." in path.parts:
            raise ValueError(f"Output path must stay below datadir: {path!s}.")
        return path
