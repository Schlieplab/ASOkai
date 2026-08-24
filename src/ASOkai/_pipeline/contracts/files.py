#!/usr/bin/env python
"""
Filename: src/ASOkai/_pipeline/contracts/files.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Version: 0.1.1
Description: File input and output declarations for pipeline steps.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from ASOkai._cwl.model import CwlToolArgument, CwlToolInput, CwlToolOutput
from ASOkai._pipeline.contracts.file_types import FileType
from ASOkai._pipeline.contracts.parameters import (
    Param,
    ScalarParam,
    _flag_for_name,
)
from ASOkai._pipeline.contracts.paths import OutputPathTemplate


@dataclass(frozen=True, init=False, eq=False)
class FileOutput(Param):
    """A produced file and the complete contract inherited by its consumers."""

    destination: OutputPathTemplate
    file_type: FileType
    doc: str | None = None
    _owner: type[Any] | None = field(
        default=None,
        init=False,
        repr=False,
        compare=False,
    )

    def __init__(
        self,
        name: str,
        *,
        destination: OutputPathTemplate | str,
        file_type: FileType | None = None,
        doc: str | None = None,
    ) -> None:
        object.__setattr__(self, "name", name)
        if isinstance(destination, str):
            destination = OutputPathTemplate(destination)
        object.__setattr__(self, "destination", destination)

        if file_type is None:
            file_type = FileType()
        if not isinstance(file_type, FileType):
            raise TypeError("FileOutput.file_type must be a FileType.")
        object.__setattr__(self, "file_type", file_type)
        object.__setattr__(self, "doc", doc)
        object.__setattr__(self, "_owner", None)

    def _validate_binding(
        self,
        owner: type[Any],
        attribute_name: str,
    ) -> None:
        """Validate a proposed producer-step binding without mutating it."""
        owner_name = getattr(owner, "name", None)
        if type(owner_name) is not str or not owner_name.strip():
            raise TypeError(f"FileOutput '{self.name}' requires a named owner.")
        if type(attribute_name) is not str or not attribute_name.strip():
            raise TypeError(f"FileOutput '{self.name}' requires an attribute name.")
        if self._owner is not None and self._owner is not owner:
            raise ValueError(
                f"FileOutput '{self.name}' is already owned by "
                f"'{self._owner.name}'."
            )

    def _bind_to(self, owner: type[Any], attribute_name: str) -> None:
        """Bind this output to exactly one producer-step attribute."""
        self._validate_binding(owner, attribute_name)
        object.__setattr__(self, "_owner", owner)

    def _require_bound(self) -> None:
        """Raise if this output is not attached to a producer step."""
        if self._owner is None:
            raise RuntimeError(
                f"FileOutput '{self.name}' is not attached to a Step."
            )

    @property
    def producer(self) -> str:
        """Return the name of the step that owns this output."""
        self._require_bound()
        assert self._owner is not None
        return self._owner.name

    def __eq__(self, other: object) -> bool:
        """Output ports compare by declaration identity."""
        return self is other

    __hash__ = object.__hash__

    @property
    def cli_prefix(self) -> str:
        """Return the generated command-line flag for this output path."""
        return _flag_for_name(self.argument_name)

    @property
    def argument_name(self) -> str:
        """Return the generated argparse destination for this output path."""
        return f"{self.name}_output"

    def working_filename(self, values: Mapping[str, Any]) -> str:
        """Derive the CWL work-directory filename from the final destination."""
        return self.destination.render(values).name

    def to_cwl_argument(self, values: Mapping[str, Any]) -> CwlToolArgument:
        """Return the fixed command-line argument for this output path."""
        return CwlToolArgument(
            prefix=self.cli_prefix,
            value_from=self.working_filename(values),
        )

    def to_cwl_output(self, values: Mapping[str, Any]) -> CwlToolOutput:
        """Return the rendered tool output declaration."""
        return CwlToolOutput(
            self.name,
            "File",
            self.working_filename(values),
            self.doc,
        )

    def add_to_parser(self, parser: argparse.ArgumentParser) -> None:
        """Add this output path as an argparse option."""
        kwargs: dict[str, Any] = {
            "dest": self.argument_name,
            "required": True,
            "type": Path,
        }
        help_text = self.doc or f"Path for the {self.name} output."
        kwargs["help"] = help_text
        parser.add_argument(self.cli_prefix, **kwargs)

    def dumps(self, value: Any) -> str:
        """Serialize one value through this output's file type."""
        return self.file_type.dumps(value)

    def write(self, path: str | Path, value: Any) -> None:
        """Write one value through this output's file type."""
        self.file_type.write(path, value)

    def validate(self, value: Any) -> None:
        """Validate a produced file against this output's file contract."""
        self.file_type.validate(value)


@dataclass(frozen=True)
class FileInput(Param):
    """A file input that inherits its behavior from a producer output."""

    source: FileOutput
    configurable_parameters: tuple[str, ...] = ()
    prefix: str | None = None
    doc: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.source, FileOutput):
            raise TypeError("FileInput.source must be a FileOutput.")
        self.source._require_bound()
        parameter_names = tuple(self.configurable_parameters)
        if any(
            type(name) is not str or not name.strip()
            for name in parameter_names
        ):
            raise ValueError(
                "FileInput.configurable_parameters must contain non-blank "
                "parameter names."
            )
        duplicates = sorted(
            {
                name
                for name in parameter_names
                if parameter_names.count(name) > 1
            }
        )
        if duplicates:
            raise ValueError(
                "FileInput.configurable_parameters contains duplicate "
                f"name(s): {', '.join(duplicates)}."
            )
        object.__setattr__(self, "configurable_parameters", parameter_names)
        for parameter_name in parameter_names:
            self.configurable_parameter(parameter_name)

    def configuration_path(self, consumer_step_name: str) -> str:
        """Return this input's standard configuration path."""
        if type(consumer_step_name) is not str or not consumer_step_name.strip():
            raise ValueError("consumer_step_name must be a non-blank string.")
        return f"steps.{consumer_step_name}.inputs.{self.name}"

    def _configured_values(
        self,
        config: Mapping[str, Any],
        consumer_step_name: str,
    ) -> Mapping[str, Any] | None:
        """Return and structurally validate this input's configuration."""
        configuration_path = self.configuration_path(consumer_step_name)
        value: Any = config
        for key in configuration_path.split("."):
            if not isinstance(value, Mapping) or key not in value:
                return None
            value = value[key]
        if not isinstance(value, Mapping):
            raise TypeError(
                f"Input configuration '{configuration_path}' must be a mapping."
            )
        unexpected = set(value) - {"path_override", "parameters"}
        if unexpected:
            names = ", ".join(sorted(str(name) for name in unexpected))
            raise ValueError(
                f"Input configuration '{configuration_path}' has unsupported "
                f"field(s): {names}."
            )
        configured_choices = [
            choice
            for choice in ("path_override", "parameters")
            if choice in value
        ]
        if len(configured_choices) != 1:
            raise ValueError(
                f"Input configuration '{configuration_path}' must define "
                "exactly one of 'path_override' or 'parameters'."
            )
        return value

    def configured_path_override(
        self,
        config: Mapping[str, Any],
        consumer_step_name: str,
    ) -> Path | None:
        """Return this input's configured path override, when present."""
        values = self._configured_values(config, consumer_step_name)
        if values is None or "path_override" not in values:
            return None
        value = values["path_override"]
        if isinstance(value, str) and not value.strip():
            raise ValueError(
                f"Input path override "
                f"'{self.configuration_path(consumer_step_name)}.path_override' "
                "must be non-blank."
            )
        try:
            return Path(value).resolve()
        except TypeError as error:
            raise TypeError(
                f"Input path override "
                f"'{self.configuration_path(consumer_step_name)}.path_override' "
                "must be a path."
            ) from error

    def configured_parameters(
        self,
        config: Mapping[str, Any],
        consumer_step_name: str,
    ) -> dict[str, Any] | None:
        """Return configured producer-parameter overrides, when present."""
        values = self._configured_values(config, consumer_step_name)
        if values is None or "parameters" not in values:
            return None
        parameters = values["parameters"]
        if not isinstance(parameters, Mapping):
            raise TypeError(
                f"Input parameters "
                f"'{self.configuration_path(consumer_step_name)}.parameters' "
                "must be a mapping."
            )
        if not parameters:
            raise ValueError(
                f"Input parameters "
                f"'{self.configuration_path(consumer_step_name)}.parameters' "
                "must not be empty."
            )
        unexpected = set(parameters) - set(self.configurable_parameters)
        if unexpected:
            names = ", ".join(sorted(str(name) for name in unexpected))
            raise ValueError(
                f"Input '{consumer_step_name}.{self.name}' does not allow "
                f"parameter(s): {names}."
            )
        return dict(parameters)

    def configurable_parameter(self, name: str) -> ScalarParam:
        """Return one producer parameter exposed by this input."""
        if name not in self.configurable_parameters:
            raise KeyError(
                f"Input '{self.name}' does not expose parameter {name!r}."
            )
        assert self.source._owner is not None
        try:
            parameter = self.source._owner.spec.parameter(name)
        except KeyError as error:
            raise ValueError(
                f"FileInput '{self.name}' exposes unknown parameter {name!r} "
                f"from producer '{self.source.producer}'."
            ) from error
        if parameter.config is None:
            raise ValueError(
                f"FileInput '{self.name}' exposes producer parameter {name!r}, "
                "but that parameter has no main configuration path."
            )
        return parameter

    @property
    def file_type(self) -> FileType:
        """Return the file type inherited from the producer output."""
        return self.source.file_type

    @property
    def cli_prefix(self) -> str:
        """Return this input's command-line flag."""
        return self.prefix or _flag_for_name(self.name)

    def parser_required(self) -> bool:
        """File inputs are always required by the step command."""
        return True

    def parser_type(self) -> Any:
        """Return the file type's argparse converter for this input."""
        return self._parse_argument

    def parser_choices(self) -> tuple[Any, ...] | None:
        """File inputs do not define argparse choices."""
        return None

    def to_cwl_input(self) -> CwlToolInput:
        """Return this input as a CWL File."""
        return CwlToolInput(
            self.name,
            "File",
            self.cli_prefix,
            self.doc,
        )

    def add_to_parser(self, parser: argparse.ArgumentParser) -> None:
        """Add this file input as an argparse option."""
        kwargs: dict[str, Any] = {
            "dest": self.name,
            "required": True,
            "type": self.parser_type(),
        }
        if self.doc:
            kwargs["help"] = self.doc
        parser.add_argument(self.cli_prefix, **kwargs)

    def loads(
        self,
        content: str,
        *,
        source: str = "<string>",
    ) -> Any:
        """Decode text through the file type inherited from the source."""
        return self.file_type.loads(
            content,
            source=source,
        )

    def read(self, path: str | Path) -> Any:
        """Read and decode through the inherited file contract."""
        return self.file_type.read(path)

    def validate(self, value: Any) -> None:
        """Validate a file against this input's inherited file contract."""
        self.file_type.validate(value)

    def _parse_argument(self, value: str) -> Any:
        try:
            return self.read(value)
        except (OSError, UnicodeError, TypeError, ValueError) as error:
            raise argparse.ArgumentTypeError(str(error)) from error
