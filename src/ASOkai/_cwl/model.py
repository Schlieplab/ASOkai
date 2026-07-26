#!/usr/bin/env python
"""
Filename: src/ASOkai/_cwl/model.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Version: 0.1.1
Description: Low-level values used to render CWL CommandLineTool documents.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any


_UNSET = object()


@dataclass(frozen=True)
class CwlToolArgument:
    """A rendered CommandLineTool argument."""

    prefix: str | None = None
    value_from: Any = _UNSET

    def to_cwl(self) -> dict[str, Any]:
        data: dict[str, Any] = {}
        if self.prefix is not None:
            data["prefix"] = self.prefix
        if self.value_from is not _UNSET:
            data["valueFrom"] = self.value_from
        return data


@dataclass(frozen=True)
class CwlToolInput:
    """A rendered CommandLineTool input with optional CLI binding metadata."""

    name: str
    type: Any
    prefix: str | None = None
    doc: str | None = None
    default: Any = _UNSET

    def to_cwl(self) -> dict[str, Any]:
        data: dict[str, Any] = {"type": deepcopy(self.type)}
        if self.doc:
            data["doc"] = self.doc
        if self.default is not _UNSET:
            data["default"] = deepcopy(self.default)
        if self.prefix:
            data["inputBinding"] = {"prefix": self.prefix}
        return data


@dataclass(frozen=True)
class CwlToolOutput:
    """A rendered CommandLineTool output with output binding metadata."""

    name: str
    type: Any
    glob: Any
    doc: str | None = None

    def to_cwl(self) -> dict[str, Any]:
        data: dict[str, Any] = {"type": deepcopy(self.type)}
        if self.doc:
            data["doc"] = self.doc
        data["outputBinding"] = {"glob": deepcopy(self.glob)}
        return data


@dataclass(frozen=True)
class CwlCommandLineToolSpec:
    """Low-level generated CommandLineTool metadata for a pipeline step."""

    base_command: list[str] | None = None
    doc: str | None = None
    requirements: dict[str, Any] = field(default_factory=dict)
    arguments: list[CwlToolArgument] = field(default_factory=list)
    inputs: list[CwlToolInput] = field(default_factory=list)
    outputs: list[CwlToolOutput] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    def command_for_step(self, step_name: str) -> list[str]:
        """Return the base command, filling the ASOkai step default."""
        return self.base_command or ["ASOkai", "step", step_name]

    def doc_for_step(self, description: str) -> str:
        """Return the tool doc, falling back to the step description."""
        return self.doc or description

    def input_names(self) -> set[str]:
        """Return declared input names."""
        return {item.name for item in self.inputs}

    def input_types(self) -> dict[str, Any]:
        """Return declared input types by input name."""
        return {item.name: deepcopy(item.type) for item in self.inputs}

    def output_names(self) -> set[str]:
        """Return declared output names."""
        return {item.name for item in self.outputs}
