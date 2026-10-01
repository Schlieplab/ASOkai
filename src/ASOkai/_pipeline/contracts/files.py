#!/usr/bin/env python
"""
Filename: src/ASOkai/_pipeline/contracts/files.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: File input and output declarations for pipeline steps.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from ASOkai._cwl.model import CwlToolArgument, CwlToolInput, CwlToolOutput
from ASOkai._pipeline.contracts.file_types import FastaFile, FileType
from ASOkai._pipeline.contracts.parameters import _flag_for_name
from ASOkai._pipeline.contracts.paths import OutputPathTemplate


@dataclass(frozen=True, init=False, eq=False)
class FileOutput:
    """A produced file and the complete contract inherited by its consumers."""

    name: str
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
        object.__setattr__(self, "file_type", file_type)
        object.__setattr__(self, "doc", doc)
        object.__setattr__(self, "_owner", None)

    def _validate_binding(self, owner: type[Any]) -> None:
        """Validate a proposed producer-step binding without mutating it."""
        if self._owner is not None and self._owner is not owner:
            raise ValueError(
                f"FileOutput '{self.name}' is already owned by "
                f"'{self._owner.name}'."
            )

    def _bind_to(self, owner: type[Any]) -> None:
        """Bind this output after its proposed owner has been validated."""
        object.__setattr__(self, "_owner", owner)

    def _require_bound(self) -> None:
        """Raise if this output is not attached to a producer step."""
        if self._owner is None:
            raise RuntimeError(f"FileOutput '{self.name}' is not attached to a Step.")

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

    def working_filename(
        self,
        config: Mapping[str, Any],
        input_configurations: (
            Mapping[
                str,
                Mapping[str, Any],
            ]
            | None
        ) = None,
    ) -> str:
        """Derive the CWL work-directory filename from the final destination."""
        return self.destination.render(config, input_configurations).name

    def to_cwl_argument(
        self,
        config: Mapping[str, Any],
        input_configurations: (
            Mapping[
                str,
                Mapping[str, Any],
            ]
            | None
        ) = None,
    ) -> CwlToolArgument:
        """Return the fixed command-line argument for this output path."""
        return CwlToolArgument(
            prefix=self.cli_prefix,
            value_from=self.working_filename(config, input_configurations),
        )

    def to_cwl_output(
        self,
        config: Mapping[str, Any],
        input_configurations: (
            Mapping[
                str,
                Mapping[str, Any],
            ]
            | None
        ) = None,
    ) -> CwlToolOutput:
        """Return the rendered tool output declaration."""
        return CwlToolOutput(
            self.name,
            self.file_type.cwl_type,
            self.working_filename(config, input_configurations),
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


@dataclass(frozen=True, init=False)
class FileInput:
    """A file input with a fixed producer or an explicit file type."""

    name: str
    source: FileOutput | None
    _declared_file_type: FileType | None = field(repr=False)
    prefix: str | None
    doc: str | None

    def __init__(
        self,
        name: str,
        source: FileOutput | None = None,
        prefix: str | None = None,
        doc: str | None = None,
        *,
        file_type: FileType | None = None,
    ) -> None:
        if (source is None) == (file_type is None):
            raise ValueError(
                "FileInput requires exactly one of source or file_type."
            )
        if source is not None:
            if not isinstance(source, FileOutput):
                raise TypeError("FileInput.source must be a FileOutput.")
            source._require_bound()
        elif not isinstance(file_type, FileType):
            raise TypeError("FileInput.file_type must be a FileType.")
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "source", source)
        object.__setattr__(self, "_declared_file_type", file_type)
        object.__setattr__(self, "prefix", prefix)
        object.__setattr__(self, "doc", doc)

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
        unexpected = set(value) - {"path_override"}
        if unexpected:
            names = ", ".join(sorted(str(name) for name in unexpected))
            raise ValueError(
                f"Input configuration '{configuration_path}' has unsupported "
                f"field(s): {names}."
            )
        if "path_override" not in value:
            raise ValueError(
                f"Input configuration '{configuration_path}' must define "
                "'path_override'."
            )
        return value

    def configured_path_override(
        self,
        config: Mapping[str, Any],
        consumer_step_name: str,
    ) -> Path | None:
        """Return this input's configured path override, when present."""
        values = self._configured_values(config, consumer_step_name)
        if values is None:
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

    def accepts_output(self, output: FileOutput) -> bool:
        """Return whether an output satisfies this input's declared contract."""
        if self.source is not None:
            return output is self.source
        if type(self.file_type) is FastaFile and self.file_type.gzip is None:
            return type(output.file_type) is FastaFile
        return (
            type(output.file_type) is type(self.file_type)
            and output.file_type == self.file_type
        )

    @property
    def file_type(self) -> FileType:
        """Return the fixed output's type or this input's declared type."""
        if self.source is not None:
            return self.source.file_type
        assert self._declared_file_type is not None
        return self._declared_file_type

    @property
    def cli_prefix(self) -> str:
        """Return this input's command-line flag."""
        return self.prefix or _flag_for_name(self.name)

    def to_cwl_input(self) -> CwlToolInput:
        """Return this input with its producer's CWL artifact type."""
        return CwlToolInput(
            self.name,
            self.file_type.cwl_type,
            self.cli_prefix,
            self.doc,
        )

    def add_to_parser(self, parser: argparse.ArgumentParser) -> None:
        """Add this file input as an argparse option."""
        kwargs: dict[str, Any] = {
            "dest": self.name,
            "required": True,
            "type": self._parse_argument,
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
