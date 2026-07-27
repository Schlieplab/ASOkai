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
from typing import Any, Generic, Mapping

from ASOkai._cwl.model import CwlToolArgument, CwlToolInput, CwlToolOutput
from ASOkai._pipeline.contracts.file_types import FileType, FileValueT
from ASOkai._pipeline.contracts.parameters import Param, _flag_for_name
from ASOkai._pipeline.contracts.paths import OutputPathTemplate


@dataclass(frozen=True, init=False, eq=False)
class FileOutput(Param, Generic[FileValueT]):
    """A produced file and the complete contract inherited by its consumers."""

    destination: OutputPathTemplate
    file_type: FileType[FileValueT]
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
        file_type: FileType[FileValueT] | None = None,
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

    def dumps(self, value: FileValueT) -> str:
        """Serialize one value through this output's file type."""
        return self.file_type.dumps(value)

    def write(self, path: str | Path, value: FileValueT) -> None:
        """Write one value through this output's file type."""
        self.file_type.write(path, value)


@dataclass(frozen=True)
class FileInput(Param, Generic[FileValueT]):
    """A file input that inherits its behavior from a producer output."""

    source: FileOutput[FileValueT]
    override: str | None = None
    prefix: str | None = None
    doc: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.source, FileOutput):
            raise TypeError("FileInput.source must be a FileOutput.")
        self.source._require_bound()

    def configured_override_path(
        self,
        config: dict,
    ) -> Path | None:
        """Return the configured override path, or None when it is not set."""
        if self.override is None:
            return None

        from ASOkai._pipeline.config import resolve

        try:
            value = resolve(config, self.override)
        except KeyError:
            return None
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            raise ValueError(
                f"Input override '{self.override}' must be a non-blank path."
            )
        try:
            return Path(value).resolve()
        except TypeError as error:
            raise TypeError(
                f"Input override '{self.override}' must be a path."
            ) from error

    @property
    def file_type(self) -> FileType[FileValueT]:
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
    ) -> FileValueT:
        """Decode text through the file type inherited from the source."""
        return self.file_type.loads(
            content,
            source=source,
        )

    def read(self, path: str | Path) -> FileValueT:
        """Read through the file type inherited from the source."""
        return self.file_type.read(path)

    def _parse_argument(self, value: str) -> FileValueT:
        try:
            return self.read(value)
        except (OSError, UnicodeError, TypeError, ValueError) as error:
            raise argparse.ArgumentTypeError(str(error)) from error
