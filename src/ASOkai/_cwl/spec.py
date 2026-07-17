#!/usr/bin/env python
"""
Filename: src/ASOkai/_cwl/spec.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Version: 0.1.1
Description: Declarative CWL CommandLineTool specs for ASOkai pipeline steps.
License: LGPL-3.0-or-later
"""
from __future__ import annotations

import argparse
from abc import ABC, abstractmethod
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from string import Formatter
from types import UnionType
from typing import Any, Literal, Mapping, Sequence, Union, get_args, get_origin

import yaml


_UNSET = object()


def enum_type(symbols: list[str]) -> dict[str, Any]:
    """Return a CWL enum type declaration."""
    return {"type": "enum", "symbols": list(symbols)}


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
        cwl_type: Any = enum_type([str(value) for value in literal_values])
    elif base is str:
        cwl_type = "string"
    elif base is int:
        cwl_type = "int"
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
    if base is Path:
        return Path
    return None


def _argparse_choices_for_annotation(annotation: Any) -> tuple[Any, ...] | None:
    """Infer argparse choices from a Literal annotation."""
    values = _literal_values(annotation)
    return values or None


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
            raise ValueError("TemplateField.first_of requires at least one input name.")
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
            raise ValueError(f"No value is available for template input(s): {names}.")
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
        for _, field_name, format_spec, conversion in Formatter().parse(self.template):
            if field_name is None:
                continue
            if not field_name or "." in field_name or "[" in field_name:
                raise ValueError(
                    f"Output path field must be a simple input name: {field_name!r}."
                )
            if format_spec or conversion:
                raise ValueError(
                    "Output path templates do not support format specs or conversions."
                )
            parsed_fields.append(field_name)

        unknown_fields = set(declared_fields) - set(parsed_fields)
        if unknown_fields:
            names = ", ".join(sorted(unknown_fields))
            raise ValueError(
                f"Output path field rule(s) are not used by the template: {names}."
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
                f"Parameter '{self.name}' is path-like; use InputParam instead."
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


@dataclass(frozen=True)
class InputParam(Param):
    """An existing file/path supplied to a step."""

    config: str | None = None
    override: str | None = None
    prefix: str | None = None
    doc: str | None = None
    default: Any = _UNSET
    required: bool | None = None
    cwl: bool = True

    @property
    def cli_prefix(self) -> str:
        """Return this input's command-line flag."""
        return self.prefix or _flag_for_name(self.name)

    def parser_required(self) -> bool:
        """Return whether argparse should require this input path."""
        if self.required is not None:
            return self.required
        return self.default is _UNSET

    def parser_type(self) -> Any:
        """Return the argparse converter for file/path inputs."""
        return Path

    def parser_choices(self) -> tuple[Any, ...] | None:
        """File/path inputs do not define argparse choices."""
        return None

    def to_cwl_input(self) -> CwlToolInput | None:
        """Return this path as a CWL File input, unless it is CLI-only."""
        if not self.cwl:
            return None
        return CwlToolInput(
            self.name,
            "File",
            self.cli_prefix,
            self.doc,
            self.default,
        )

    def add_to_parser(self, parser: argparse.ArgumentParser) -> None:
        """Add this file/path input as an argparse option."""
        kwargs: dict[str, Any] = {
            "dest": self.name,
            "required": self.parser_required(),
            "type": Path,
        }
        if self.default is not _UNSET:
            kwargs["default"] = deepcopy(self.default)
        if self.doc:
            kwargs["help"] = self.doc
        parser.add_argument(self.cli_prefix, **kwargs)


@dataclass(frozen=True, init=False)
class OutputParam(Param):
    """A produced file with a stable temporary name and destination path."""

    temp_filename: str
    destination: OutputPathTemplate
    doc: str | None = None

    def __init__(
        self,
        name: str,
        *,
        temp_filename: str,
        destination: OutputPathTemplate | str | None = None,
        doc: str | None = None,
    ) -> None:
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "temp_filename", temp_filename)
        if destination is None:
            destination = OutputPathTemplate(temp_filename)
        elif isinstance(destination, str):
            destination = OutputPathTemplate(destination)
        object.__setattr__(self, "destination", destination)
        object.__setattr__(self, "doc", doc)
        self.__post_init__()

    def __post_init__(self) -> None:
        if (
            not self.temp_filename
            or Path(self.temp_filename).name != self.temp_filename
            or "{" in self.temp_filename
            or "}" in self.temp_filename
        ):
            raise ValueError(
                "OutputParam.temp_filename must be one stable temporary filename."
            )

    @property
    def cli_prefix(self) -> str:
        """Return the generated command-line flag for this output path."""
        return _flag_for_name(self.argument_name)

    @property
    def argument_name(self) -> str:
        """Return the generated argparse destination for this output path."""
        return f"{self.name}_output"

    def to_cwl_argument(self) -> CwlToolArgument:
        """Return the fixed command-line argument for this output path."""
        return CwlToolArgument(
            prefix=self.cli_prefix,
            value_from=self.temp_filename,
        )

    def to_cwl_output(self) -> CwlToolOutput:
        """Return the rendered tool output declaration."""
        return CwlToolOutput(
            self.name,
            "File",
            self.temp_filename,
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


@dataclass(frozen=True)
class StepSpec:
    """Source-of-truth metadata for a pipeline step."""

    params: Sequence[ScalarParam] = field(default_factory=tuple)
    inputs: Sequence[InputParam] = field(default_factory=tuple)
    outputs: Sequence[OutputParam] = field(default_factory=tuple)
    base_command: list[str] | None = None
    doc: str | None = None
    requirements: dict[str, Any] = field(default_factory=dict)
    arguments: Sequence[CwlToolArgument] = field(default_factory=tuple)
    extra: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Reject declarations that would produce ambiguous CLI or CWL ports."""
        object.__setattr__(self, "params", tuple(self.params))
        object.__setattr__(self, "inputs", tuple(self.inputs))
        object.__setattr__(self, "outputs", tuple(self.outputs))
        object.__setattr__(self, "arguments", tuple(self.arguments))

        self._require_unique("parameter", [param.name for param in self.params])
        self._require_unique("input", [item.name for item in self.inputs])
        self._require_unique("output", [output.name for output in self.outputs])

        authored_inputs = [param.name for param in self.params]
        authored_inputs.extend(item.name for item in self.inputs)
        self._require_unique("parameter/input", authored_inputs)

        cwl_inputs = [param.name for param in self.params if param.cwl]
        cwl_inputs.extend(item.name for item in self.inputs if item.cwl)
        self._require_unique("generated CWL input", cwl_inputs)

        declared_cwl_inputs = {
            param.name for param in self.params if param.cwl
        }
        declared_cwl_inputs.update(item.name for item in self.inputs if item.cwl)
        for output in self.outputs:
            missing_inputs = output.destination.input_names() - declared_cwl_inputs
            if missing_inputs:
                names = ", ".join(sorted(missing_inputs))
                raise ValueError(
                    f"Output '{output.name}' path references undeclared CWL "
                    f"input(s): {names}."
                )

        reserved = {
            "cwlVersion", "class", "baseCommand", "doc", "requirements",
            "arguments", "inputs", "outputs",
        }
        conflicting_extra = reserved.intersection(self.extra)
        if conflicting_extra:
            names = ", ".join(sorted(conflicting_extra))
            raise ValueError(f"StepSpec.extra cannot replace reserved keys: {names}.")

    @staticmethod
    def _require_unique(label: str, names: list[str]) -> None:
        duplicates = sorted({name for name in names if names.count(name) > 1})
        if duplicates:
            joined = ", ".join(duplicates)
            raise ValueError(f"Duplicate {label} name(s): {joined}.")

    def to_cwl_tool_spec(self) -> CwlCommandLineToolSpec:
        """Return the low-level CommandLineTool spec generated from this step spec."""
        inputs = [
            item
            for param in self.params
            if (item := param.to_cwl_input()) is not None
        ]
        inputs.extend(
            item
            for input_param in self.inputs
            if (item := input_param.to_cwl_input()) is not None
        )
        return CwlCommandLineToolSpec(
            base_command=self.base_command,
            doc=self.doc,
            requirements=deepcopy(self.requirements),
            arguments=[
                *self.arguments,
                *(output.to_cwl_argument() for output in self.outputs),
            ],
            inputs=inputs,
            outputs=[output.to_cwl_output() for output in self.outputs],
            extra=deepcopy(self.extra),
        )

    def config_map(self) -> dict[str, str]:
        """Return CWL input names mapped to config dot paths."""
        result = {
            param.name: param.config
            for param in self.params
            if param.cwl and param.config
        }
        result.update(
            {
                item.name: item.config
                for item in self.inputs
                if item.cwl and item.config
            }
        )
        return result

    def input_overrides(self) -> dict[str, str]:
        """Return CWL input names mapped to optional file override config paths."""
        return {
            item.name: item.override
            for item in self.inputs
            if item.cwl and item.override
        }

    def output_names(self) -> tuple[str, ...]:
        """Return produced output names in declaration order."""
        return tuple(output.name for output in self.outputs)

    def output_relative_path(
        self,
        name: str,
        values: Mapping[str, Any],
    ) -> PurePosixPath:
        """Render one declared path relative to the configured data directory."""
        for output in self.outputs:
            if output.name == name:
                return output.destination.render(values)
        raise KeyError(f"Unknown step output: {name!r}.")

    def validate_output_paths(self, output_paths: dict[str, Path]) -> None:
        """Ensure runtime output paths exactly implement the declared outputs."""
        declared = set(self.output_names())
        actual = set(output_paths)
        if declared == actual:
            return

        missing = ", ".join(sorted(declared - actual)) or "none"
        unexpected = ", ".join(sorted(actual - declared)) or "none"
        raise ValueError(
            "Step output_paths() does not match StepSpec outputs "
            f"(missing: {missing}; unexpected: {unexpected})."
        )

    def build_parser(
        self,
        *,
        description: str | None = None,
    ) -> argparse.ArgumentParser:
        """Build an argparse parser from declared step parameters."""
        parser = argparse.ArgumentParser(description=description)
        for param in self.params:
            param.add_to_parser(parser)
        for input_param in self.inputs:
            input_param.add_to_parser(parser)
        for output in self.outputs:
            output.add_to_parser(parser)
        return parser


class BaseCwlGenerator:
    """Shared YAML rendering behavior for generated CWL documents."""

    cwl_version = "v1.2"

    def dump(self, doc: dict[str, Any]) -> str:
        return yaml.safe_dump(doc, default_flow_style=False, sort_keys=False)


class StepCwlGenerator(BaseCwlGenerator):
    """Render a step's CwlCommandLineToolSpec as a CWL CommandLineTool document."""

    def document(self, step) -> dict[str, Any]:
        spec = step.cwl_spec
        doc: dict[str, Any] = {
            "cwlVersion": self.cwl_version,
            "class": "CommandLineTool",
            "baseCommand": spec.command_for_step(step.name),
            "doc": spec.doc_for_step(step.description),
        }
        if spec.requirements:
            doc["requirements"] = deepcopy(spec.requirements)
        if spec.arguments:
            doc["arguments"] = [argument.to_cwl() for argument in spec.arguments]
        doc["inputs"] = {item.name: item.to_cwl() for item in spec.inputs}
        doc["outputs"] = {item.name: item.to_cwl() for item in spec.outputs}
        doc.update(deepcopy(spec.extra))
        return doc

    def render(self, step, *, shebang: bool = True) -> str:
        text = self.dump(self.document(step))
        if shebang:
            return f"#!/usr/bin/env cwl-runner\n{text}"
        return text


def step_cwl_filename(step) -> str:
    """Return the generated CommandLineTool filename for a step."""
    return f"{step.name}.cwl"


def step_cwl_run_path(step) -> str:
    """Return the relative run path used inside generated jobs."""
    return f"steps/{step_cwl_filename(step)}"
