#!/usr/bin/env python
"""
Filename: src/ASOkai/_pipeline/contracts/parameters.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Version: 0.1.1
Description: Scalar parameter declarations for pipeline steps.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

import argparse
from abc import ABC, abstractmethod
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from types import UnionType
from typing import (
    Any,
    Literal,
    Union,
    get_args,
    get_origin,
)

from ASOkai._cwl.model import CwlToolInput, _UNSET


def _flag_for_name(name: str) -> str:
    """Return the default CLI flag for a Python-style parameter name."""
    return f"--{name.replace('_', '-')}"


def _is_optional(annotation: Any) -> bool:
    """Return whether an annotation allows None."""
    origin = get_origin(annotation)
    if origin in (Union, UnionType):
        return type(None) in get_args(annotation)
    return False


def _strip_optional(annotation: Any) -> Any:
    """Return the non-None member of an optional annotation."""
    if not _is_optional(annotation):
        return annotation
    args = [arg for arg in get_args(annotation) if arg is not type(None)]
    return args[0] if len(args) == 1 else annotation


def _literal_values(annotation: Any) -> tuple[Any, ...]:
    """Return Literal values for an annotation, if present."""
    base = _strip_optional(annotation)
    if get_origin(base) is Literal:
        return get_args(base)
    return ()


def _cwl_type_for_annotation(annotation: Any) -> Any:
    """Infer a CWL type declaration from a Python annotation."""
    optional = _is_optional(annotation)
    base = _strip_optional(annotation)
    literal_values = _literal_values(annotation)

    if literal_values:
        cwl_type: Any = {
            "type": "enum",
            "symbols": [str(value) for value in literal_values],
        }
    elif base is str:
        cwl_type = "string"
    elif base is int:
        cwl_type = "int"
    elif base is float:
        cwl_type = "double"
    elif base is bool:
        cwl_type = "boolean"
    elif base is Path:
        cwl_type = "File"
    else:
        raise TypeError(f"Unsupported CWL parameter annotation: {annotation!r}")

    if optional:
        if isinstance(cwl_type, str):
            return f"{cwl_type}?"
        return ["null", cwl_type]
    return cwl_type


def _argparse_type_for_annotation(annotation: Any) -> Any:
    """Infer an argparse type callable from a Python annotation."""
    base = _strip_optional(annotation)
    if _literal_values(annotation):
        return None
    if base is int:
        return int
    if base is float:
        return float
    if base is bool:
        return _parse_boolean
    if base is Path:
        return Path
    return None


def _parse_boolean(value: str) -> bool:
    """Parse the lowercase boolean spelling used by ASOkai configuration."""
    if value == "true":
        return True
    if value == "false":
        return False
    raise argparse.ArgumentTypeError("expected 'true' or 'false'")


def _argparse_choices_for_annotation(annotation: Any) -> tuple[Any, ...] | None:
    """Infer argparse choices from a Literal annotation."""
    values = _literal_values(annotation)
    return values or None


@dataclass(frozen=True)
class Param(ABC):
    """Base contract shared by scalar, input-file, and output-file parameters."""

    name: str

    @property
    @abstractmethod
    def cli_prefix(self) -> str:
        """Return this parameter's command-line flag."""
        ...

    @abstractmethod
    def add_to_parser(self, parser: argparse.ArgumentParser) -> None:
        """Add this parameter as an argparse option."""
        ...

    @abstractmethod
    def validate(self, value: Any) -> None:
        """Validate one value against this parameter's contract."""
        ...


@dataclass(frozen=True)
class ScalarParam(Param):
    """A scalar step parameter that can produce CWL, CLI, and config metadata."""

    annotation: Any
    config: str | None = None
    prefix: str | None = None
    doc: str | None = None
    default: Any = _UNSET
    required: bool | None = None
    cwl: bool = True
    cwl_type: Any = _UNSET
    parser_annotation: Any = _UNSET

    def __post_init__(self) -> None:
        if _strip_optional(self.annotation) is Path:
            raise TypeError(
                f"Parameter '{self.name}' is path-like; use FileInput instead."
            )

    @property
    def cli_prefix(self) -> str:
        """Return this parameter's command-line flag."""
        return self.prefix or _flag_for_name(self.name)

    def inferred_cwl_type(self) -> Any:
        """Return this parameter's CWL type."""
        if self.cwl_type is not _UNSET:
            return deepcopy(self.cwl_type)
        return _cwl_type_for_annotation(self.annotation)

    def inferred_parser_annotation(self) -> Any:
        """Return the annotation used for argparse behavior."""
        if self.parser_annotation is not _UNSET:
            return self.parser_annotation
        return self.annotation

    def parser_required(self) -> bool:
        """Return whether argparse should require this parameter."""
        if self.required is not None:
            return self.required
        if self.default is not _UNSET:
            return False
        return not _is_optional(self.inferred_parser_annotation())

    def parser_type(self) -> Any:
        """Return the argparse type callable inferred for this parameter."""
        return _argparse_type_for_annotation(self.inferred_parser_annotation())

    def parser_choices(self) -> tuple[Any, ...] | None:
        """Return argparse choices inferred for this parameter."""
        return _argparse_choices_for_annotation(self.inferred_parser_annotation())

    def validate(self, value: Any) -> None:
        """Validate one resolved scalar value against this parameter contract."""
        annotation = self.annotation
        if value is None:
            if _is_optional(annotation):
                return
            raise ValueError(f"parameter '{self.name}' does not accept null")

        accepted_values = _literal_values(annotation)
        if accepted_values:
            if any(
                type(value) is type(accepted_value)
                and value == accepted_value
                for accepted_value in accepted_values
            ):
                return
            accepted = ", ".join(repr(item) for item in accepted_values)
            raise ValueError(
                f"parameter '{self.name}' must be one of {accepted}; "
                f"received {value!r}"
            )

        expected_type = _strip_optional(annotation)
        if expected_type in (str, int, float, bool):
            if type(value) is expected_type:
                return
            raise ValueError(
                f"parameter '{self.name}' must be {expected_type.__name__}; "
                f"received {type(value).__name__}"
            )

        raise TypeError(
            f"parameter '{self.name}' has unsupported scalar annotation "
            f"{annotation!r}"
        )

    def to_cwl_input(self) -> CwlToolInput | None:
        """Return this parameter as a rendered tool input, if needed."""
        if not self.cwl:
            return None
        return CwlToolInput(
            self.name,
            self.inferred_cwl_type(),
            self.cli_prefix,
            self.doc,
            self.default,
        )

    def add_to_parser(self, parser: argparse.ArgumentParser) -> None:
        """Add this parameter as an argparse option."""
        kwargs: dict[str, Any] = {
            "dest": self.name,
            "required": self.parser_required(),
        }
        parser_type = self.parser_type()
        choices = self.parser_choices()
        if parser_type is not None:
            kwargs["type"] = parser_type
        if choices is not None:
            kwargs["choices"] = choices
        if self.default is not _UNSET:
            kwargs["default"] = deepcopy(self.default)
        if self.doc:
            kwargs["help"] = self.doc
        parser.add_argument(self.cli_prefix, **kwargs)
