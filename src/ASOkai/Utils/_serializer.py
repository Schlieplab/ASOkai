#!/usr/bin/env python
"""
Filename: src/ASOkai/Utils/_serializer.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: This file defines the Serializable class for serializing and deserializing objects.
License: LGPL-3.0-or-later
"""
from __future__ import annotations

import inspect
import sys
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import fields, is_dataclass
from functools import cache
from types import NoneType, SimpleNamespace, UnionType
from typing import (
    Any,
    ClassVar,
    Literal,
    Self,
    Union,
    cast,
    get_args,
    get_origin,
    get_type_hints,
)

from Bio.Seq import Seq

from ..Types import Scalar


_REFERENCE_KEY = "$ref"
_OBJECT_POINTER_PREFIX = "#/objects/"


class _GraphCycleError(ValueError):
    """A Serializable graph contains a cycle the format cannot represent."""


class Serializable:
    """
    Base class for objects that can be serialized to a dictionary.
    """
    
    _serialized_names: ClassVar[dict[str, str]] = {}
    _flattened_attributes: ClassVar[frozenset[str]] = frozenset()
    _non_serializable_attrs: ClassVar[set[str]] = set()

    @classmethod
    @cache
    def _inherited_serialized_names(cls) -> dict[str, str]:
        """Return attribute-to-document names declared across the hierarchy."""
        serialized_names: dict[str, str] = {}
        for base in reversed(cls.__mro__):
            serialized_names.update(
                base.__dict__.get("_serialized_names", {})
            )
        return serialized_names

    @classmethod
    @cache
    def _inherited_flattened_attributes(cls) -> frozenset[str]:
        """Return flattened attribute names declared across the hierarchy."""
        flattened_attributes: set[str] = set()
        for base in reversed(cls.__mro__):
            flattened_attributes.update(
                base.__dict__.get("_flattened_attributes", frozenset())
            )
        return frozenset(flattened_attributes)

    @classmethod
    @cache
    def _serialized_field_types(cls) -> dict[str, Any]:
        """Return serialized field names and their declared Python types."""
        serialized_fields: dict[str, Any] = {}
        serialized_names = cls._inherited_serialized_names()
        flattened_attributes = cls._inherited_flattened_attributes()
        serialized_private_fields = {
            *serialized_names,
            *flattened_attributes,
        }

        for class_in_hierarchy in reversed(cls.__mro__):
            declared_fields = _declared_field_types(
                class_in_hierarchy,
                serialized_private_fields=serialized_private_fields,
            )
            for field_name, field_type in declared_fields.items():
                if field_name in cls._non_serializable_attrs:
                    continue

                if field_name not in flattened_attributes:
                    serialized_name = serialized_names.get(
                        field_name,
                        field_name,
                    )
                    serialized_fields[serialized_name] = field_type
                    continue

                if not isinstance(field_type, type):
                    raise TypeError(
                        f"Flattened field {field_name!r} on {cls.__name__} "
                        "must have a concrete class annotation."
                    )
                for flattened_class in reversed(field_type.__mro__):
                    serialized_fields.update(
                        _declared_field_types(flattened_class)
                    )

        return serialized_fields

    @classmethod
    @cache
    def _constructor_parameters(
        cls,
    ) -> Mapping[str, inspect.Parameter]:
        """Return the parameters accepted by this type's constructor."""
        return inspect.signature(cls.__init__).parameters

    @classmethod
    @cache
    def _accepts_extra_fields(cls) -> bool:
        """Return whether the constructor accepts keyword metadata."""
        return any(
            parameter.kind is inspect.Parameter.VAR_KEYWORD
            for parameter in cls._constructor_parameters().values()
        )

    @classmethod
    def _known_serializable_types(
        cls,
    ) -> tuple[type[Serializable], ...]:
        """Return this type and every currently loaded Serializable subtype."""
        known_types: list[type[Serializable]] = []
        pending = [cls]
        seen: set[type[Serializable]] = set()
        while pending:
            candidate = pending.pop()
            if candidate in seen:
                continue
            seen.add(candidate)
            known_types.append(candidate)
            pending.extend(candidate.__subclasses__())
        return tuple(known_types)

    def __init__(self, **kwargs: Any) -> None:
        """
        Initialize with keyword arguments.
        Extra values are retained as instance attributes and validated when
        serialized.
        """
        for key, value in kwargs.items():
            setattr(self, key, value)

    def to_dict(self) -> dict[str, Any]:
        """Convert this object to its standalone record representation."""
        return self._to_record()

    def _to_record(
        self,
        *,
        graph: _GraphEncoder | None = None,
    ) -> dict[str, Any]:
        """Serialize one object record, optionally hoisting nested objects."""
        data: dict[str, Any] = {
            "__class__": self.__class__.__name__,
            "__module__": self.__class__.__module__,
        }
        for key, value in self.__dict__.items():
            data.update(self._serialize_attribute(key, value, graph=graph))
        return data

    def _serialize_attribute(
        self,
        attribute_name: str,
        value: Any,
        *,
        graph: _GraphEncoder | None = None,
    ) -> dict[str, Any]:
        """
        Serialize an attribute to a dictionary.
        """
        if attribute_name in self._non_serializable_attrs:
            return {}
        if attribute_name in type(self)._inherited_flattened_attributes():
            serialized_value = self._serialize_value(value, graph=graph)
            if not isinstance(serialized_value, dict):
                raise TypeError(
                    f"Flattened attribute {attribute_name!r} must serialize "
                    "to a mapping."
                )
            return serialized_value

        serialized_name = type(self)._inherited_serialized_names().get(
            attribute_name,
            attribute_name,
        )
        if serialized_name not in type(self)._serialized_field_types():
            _require_plain_json_data(value)
        return {serialized_name: self._serialize_value(value, graph=graph)}

    def _serialize_value(
        self,
        value: Any,
        *,
        graph: _GraphEncoder | None = None,
    ) -> Any:
        """
        Default method to serialize a value to a dictionary.
        """
        if isinstance(value, Seq):
            return str(value)
        elif _is_scalar(value):
            return value
        elif isinstance(value, Serializable):
            if graph is not None:
                return graph.encode_object(value)
            return value.to_dict()
        elif is_dataclass(value) and not isinstance(value, type):
            return {
                field.name: self._serialize_value(
                    getattr(value, field.name),
                    graph=graph,
                )
                for field in fields(value)
                if field.init
            }
        elif isinstance(value, dict):
            if any(type(key) is not str for key in value):
                raise TypeError("Serialized mappings must have string keys.")
            return {
                key: self._serialize_value(item, graph=graph)
                for key, item in value.items()
            }
        elif isinstance(value, list):
            return [self._serialize_value(item, graph=graph) for item in value]
        else:
            raise TypeError(f"Cannot serialize type {type(value).__name__}")

    @classmethod
    def _deserialize_value(
        cls,
        value_data: Any,
        expected_type: Any = Any,
        *,
        graph: _GraphDecoder | None = None,
    ) -> Any:
        """
        Default method to deserialize a value from a dictionary.
        """
        if expected_type is Any:
            if isinstance(value_data, list):
                return [
                    cls._deserialize_value(item, graph=graph)
                    for item in value_data
                ]
            if isinstance(value_data, dict):
                return {
                    key: cls._deserialize_value(value, graph=graph)
                    for key, value in value_data.items()
                }
            return value_data

        origin = get_origin(expected_type)
        type_arguments = get_args(expected_type)

        if origin in (Union, UnionType):
            errors: list[TypeError | ValueError] = []
            for alternative in type_arguments:
                try:
                    return cls._deserialize_value(
                        value_data,
                        alternative,
                        graph=graph,
                    )
                except (TypeError, ValueError) as error:
                    errors.append(error)
            raise TypeError(
                f"Value {value_data!r} does not match {expected_type!r}."
            ) from errors[-1]

        if origin is Literal:
            if any(
                type(value_data) is type(option) and value_data == option
                for option in type_arguments
            ):
                return value_data
            raise ValueError(
                f"Value {value_data!r} is not one of {type_arguments!r}."
            )

        if expected_type is Seq:
            if type(value_data) is not str:
                raise TypeError("Seq values must be serialized as strings.")
            return Seq(value_data)

        if expected_type is NoneType:
            if value_data is not None:
                raise TypeError("Expected null.")
            return None

        if expected_type in (str, int, float, bool):
            if expected_type is float:
                if type(value_data) not in (int, float):
                    raise TypeError("Expected a number.")
                return float(value_data)
            if type(value_data) is not expected_type:
                raise TypeError(
                    f"Expected {expected_type.__name__}; received "
                    f"{type(value_data).__name__}."
                )
            return value_data

        if origin is list:
            if not isinstance(value_data, list):
                raise TypeError("Expected a list.")
            if len(type_arguments) != 1:
                raise TypeError(
                    "Serialized list annotations require one item type."
                )
            item_type = type_arguments[0]
            return [
                cls._deserialize_value(item, item_type, graph=graph)
                for item in value_data
            ]

        if origin in (dict, Mapping):
            if not isinstance(value_data, dict):
                raise TypeError("Expected a mapping.")
            if len(type_arguments) != 2 or type_arguments[0] is not str:
                raise TypeError("Serialized mappings must have string keys.")
            value_type = type_arguments[1]
            return {
                cls._deserialize_value(key, str, graph=graph): cls._deserialize_value(
                    value,
                    value_type,
                    graph=graph,
                )
                for key, value in value_data.items()
            }

        if (
            isinstance(expected_type, type)
            and issubclass(expected_type, Serializable)
        ):
            if graph is not None:
                if _is_reference(value_data):
                    return graph.resolve(value_data, expected_type)
                if not isinstance(value_data, dict):
                    raise TypeError("Expected an inline record or $ref.")
                return expected_type._from_record(value_data, graph=graph)
            if not isinstance(value_data, dict):
                raise TypeError("Expected a serialized object mapping.")
            return expected_type._from_record(value_data)

        if isinstance(expected_type, type) and is_dataclass(expected_type):
            if not isinstance(value_data, dict):
                raise TypeError("Expected a dataclass mapping.")
            constructor_fields = {
                field.name
                for field in fields(expected_type)
                if field.init
            }
            unexpected_fields = set(value_data) - constructor_fields
            if unexpected_fields:
                names = ", ".join(sorted(unexpected_fields))
                raise ValueError(
                    f"Unexpected fields for {expected_type.__name__}: {names}."
                )
            field_types = get_type_hints(expected_type)
            constructor_values = {
                field.name: cls._deserialize_value(
                    value_data[field.name],
                    field_types.get(field.name, Any),
                    graph=graph,
                )
                for field in fields(expected_type)
                if field.init and field.name in value_data
            }
            return expected_type(**constructor_values)

        raise TypeError(
            f"Cannot deserialize values annotated as {expected_type!r}."
        )

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
    ) -> Self:
        """
        Create an object from a dictionary.
        """
        return cast(Self, cls._from_record(data))

    @classmethod
    def _from_record(
        cls,
        data: dict[str, Any],
        *,
        graph: _GraphDecoder | None = None,
    ) -> Serializable:
        """Construct one object from a standalone or graph record."""
        if not (
            isinstance(data, dict) and "__class__" in data and "__module__" in data
        ):
            raise ValueError("Data is not a valid serialized object dictionary.")

        data = data.copy()
        module_name = data.pop("__module__")
        class_name = data.pop("__class__")
        cls_from_data = cls._resolve_serialized_class(
            module_name,
            class_name,
        )

        constructor_parameters = cls_from_data._constructor_parameters()
        accepts_extra_fields = cls_from_data._accepts_extra_fields()
        serialized_field_types = cls_from_data._serialized_field_types()
        init_args: dict[str, Any] = {}

        for serialized_name, value in data.items():
            if serialized_name not in serialized_field_types:
                parameter = constructor_parameters.get(serialized_name)
                if parameter is not None and parameter.kind not in (
                    inspect.Parameter.VAR_POSITIONAL,
                    inspect.Parameter.VAR_KEYWORD,
                ):
                    raise ValueError(
                        f"Constructor parameter {serialized_name!r} is not a "
                        f"serialized field of {cls_from_data.__name__}."
                    )
                if not accepts_extra_fields:
                    raise ValueError(
                        f"Unexpected serialized field {serialized_name!r} for "
                        f"{cls_from_data.__name__}."
                    )
                init_args[serialized_name] = cls_from_data._deserialize_value(
                    value,
                    graph=graph,
                )
                continue

            parameter = constructor_parameters.get(serialized_name)
            if parameter is None and not accepts_extra_fields:
                raise ValueError(
                    f"Serialized field {serialized_name!r} does not map to "
                    f"a constructor argument of {cls_from_data.__name__}."
                )
            if (
                parameter is not None
                and parameter.kind is inspect.Parameter.POSITIONAL_ONLY
            ):
                raise TypeError(
                    f"Serializable constructor argument {serialized_name!r} "
                    "cannot be positional-only."
                )
            init_args[serialized_name] = cls_from_data._deserialize_value(
                value,
                serialized_field_types[serialized_name],
                graph=graph,
            )

        return cls_from_data(**init_args)

    @classmethod
    def _resolve_serialized_class(
        cls,
        module_name: Any,
        class_name: Any,
    ) -> type[Serializable]:
        """Resolve metadata among the expected, already-loaded classes."""
        if type(module_name) is not str or type(class_name) is not str:
            raise TypeError(
                "Serialized __module__ and __class__ values must be strings."
            )

        matches = [
            candidate
            for candidate in cls._known_serializable_types()
            if (
                candidate.__module__ == module_name
                and candidate.__name__ == class_name
            )
        ]
        if not matches:
            raise ValueError(
                f"Unknown {cls.__name__} implementation "
                f"{module_name}.{class_name}."
            )
        if len(matches) > 1:
            raise ValueError(
                f"Ambiguous {cls.__name__} implementation "
                f"{module_name}.{class_name}."
            )
        return matches[0]


def _declared_field_types(
    declaring_class: type[Any],
    *,
    serialized_private_fields: Iterable[str] = (),
) -> dict[str, Any]:
    """Resolve serializable fields declared directly by one class."""
    serialized_private_field_names = set(serialized_private_fields)
    annotations = {
        field_name: annotation
        for field_name, annotation in declaring_class.__dict__.get(
            "__annotations__",
            {},
        ).items()
        if (
            not field_name.startswith("_")
            or field_name in serialized_private_field_names
        )
    }
    if not annotations:
        return {}

    annotation_holder = SimpleNamespace(__annotations__=annotations)
    resolved_fields = get_type_hints(
        annotation_holder,
        globalns=vars(sys.modules[declaring_class.__module__]),
        localns=dict(vars(declaring_class)),
    )
    return {
        field_name: field_type
        for field_name, field_type in resolved_fields.items()
        if get_origin(field_type) is not ClassVar
    }


def _is_scalar(value: Any) -> bool:
    """Return whether a value is a supported serialized scalar."""
    return value is None or type(value) in (str, int, float, bool)


def _require_plain_json_data(value: Any) -> None:
    """Reject object values in undeclared metadata that cannot round-trip."""
    if _is_scalar(value):
        return
    if isinstance(value, list):
        for item in value:
            _require_plain_json_data(item)
        return
    if isinstance(value, dict):
        if any(type(key) is not str for key in value):
            raise TypeError("Serialized mappings must have string keys.")
        for item in value.values():
            _require_plain_json_data(item)
        return
    raise TypeError(
        "Undeclared Serializable attributes must contain plain JSON data; "
        f"received {type(value).__name__}."
    )


class _GraphEncoder:
    """Keep unique objects inline and hoist repeatedly referenced instances."""

    def __init__(self) -> None:
        self.objects: dict[str, dict[str, Any]] = {}
        self._instances: dict[int, Serializable] = {}
        self._reference_counts: Counter[int] = Counter()
        self._seen_objects: set[int] = set()
        self._keys_by_identity: dict[int, str] = {}
        self._active: set[int] = set()

    def encode(self, value: Any) -> dict[str, Any]:
        self._count_references(value)
        shared = [
            instance
            for identity, instance in self._instances.items()
            if self._reference_counts[identity] > 1
        ]
        class_counts = Counter(type(instance).__name__ for instance in shared)
        next_index: Counter[str] = Counter()
        for instance in shared:
            class_name = type(instance).__name__
            key = (
                class_name
                if class_counts[class_name] == 1
                else f"{class_name}-{next_index[class_name]}"
            )
            next_index[class_name] += 1
            self._keys_by_identity[id(instance)] = key
        return {
            "root": self._encode_value(value),
            "objects": self.objects,
        }

    def _count_references(self, value: Any) -> None:
        """Count incoming object edges while visiting each object's fields once."""
        if isinstance(value, Serializable):
            identity = id(value)
            self._instances[identity] = value
            self._reference_counts[identity] += 1
            if identity in self._active:
                raise _GraphCycleError(
                    "Cyclic Serializable references are not supported."
                )
            if identity in self._seen_objects:
                return
            self._seen_objects.add(identity)
            children = (
                item
                for name, item in value.__dict__.items()
                if name not in value._non_serializable_attrs
            )
        elif is_dataclass(value) and not isinstance(value, type):
            identity = id(value)
            children = (
                getattr(value, field.name)
                for field in fields(value)
                if field.init
            )
        elif isinstance(value, dict):
            identity = id(value)
            children = iter(value.values())
        elif isinstance(value, list):
            identity = id(value)
            children = iter(value)
        else:
            return

        if identity in self._active:
            raise _GraphCycleError("Cyclic serialized values are not supported.")
        self._active.add(identity)
        try:
            for child in children:
                self._count_references(child)
        finally:
            self._active.remove(identity)

    def encode_object(self, value: Serializable) -> dict[str, Any]:
        identity = id(value)
        key = self._keys_by_identity.get(identity)
        if identity in self._active:
            raise _GraphCycleError(
                "Cyclic Serializable references are not supported."
            )
        if key is not None and key in self.objects:
            return {_REFERENCE_KEY: _object_pointer(key)}
        if key is not None:
            self.objects[key] = {}
        self._active.add(identity)
        try:
            record = value._to_record(graph=self)
        finally:
            self._active.remove(identity)
        if key is None:
            return record
        self.objects[key] = record
        return {_REFERENCE_KEY: _object_pointer(key)}

    def _encode_value(self, value: Any) -> Any:
        if isinstance(value, Serializable):
            return self.encode_object(value)
        if isinstance(value, Seq):
            return str(value)
        if _is_scalar(value):
            return value
        if is_dataclass(value) and not isinstance(value, type):
            return {
                field.name: self._encode_value(getattr(value, field.name))
                for field in fields(value)
                if field.init
            }
        if isinstance(value, dict):
            if any(type(key) is not str for key in value):
                raise TypeError("Serialized mappings must have string keys.")
            return {
                key: self._encode_value(item)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [self._encode_value(item) for item in value]
        raise TypeError(f"Cannot serialize type {type(value).__name__}")


class _GraphValidator:
    """Validate typed references without constructing domain objects."""

    def __init__(self, data: Mapping[str, Any]) -> None:
        _validate_graph_envelope(data)
        objects = data["objects"]
        assert isinstance(objects, dict)
        self.root = data["root"]
        self._records: dict[str, dict[str, Any]] = {}
        for key, record in objects.items():
            if type(key) is not str or not isinstance(record, dict):
                raise TypeError(
                    "Serializable graph objects must map string keys to records."
                )
            self._records[key] = record
        self._visited: set[str] = set()
        self._active: set[str] = set()

    def validate(self, expected_type: Any) -> None:
        self._validate_value(self.root, expected_type)
        unused = set(self._records) - self._visited
        if unused:
            names = ", ".join(sorted(unused))
            raise ValueError(f"Unreferenced Serializable graph objects: {names}.")

    def _validate_value(self, value: Any, expected_type: Any) -> None:
        if expected_type is Any:
            return

        origin = get_origin(expected_type)
        type_arguments = get_args(expected_type)

        if origin in (Union, UnionType):
            errors: list[TypeError | ValueError] = []
            visited_before = self._visited.copy()
            for alternative in type_arguments:
                try:
                    self._validate_value(value, alternative)
                    return
                except (TypeError, ValueError) as error:
                    if isinstance(error, _GraphCycleError):
                        raise
                    self._visited = visited_before.copy()
                    errors.append(error)
            raise TypeError(
                f"Value {value!r} does not match {expected_type!r}."
            ) from errors[-1]

        if origin is Literal:
            if not any(
                type(value) is type(option) and value == option
                for option in type_arguments
            ):
                raise ValueError(
                    f"Value {value!r} is not one of {type_arguments!r}."
                )
            return

        if expected_type is Seq:
            if type(value) is not str:
                raise TypeError("Seq values must be serialized as strings.")
            return
        if expected_type is NoneType:
            if value is not None:
                raise TypeError("Expected null.")
            return
        if expected_type in (str, int, float, bool):
            accepted_types = (int, float) if expected_type is float else (expected_type,)
            if type(value) not in accepted_types:
                raise TypeError(f"Expected {expected_type.__name__}.")
            return

        if origin is list:
            if not isinstance(value, list) or len(type_arguments) != 1:
                raise TypeError("Expected a typed list.")
            for item in value:
                self._validate_value(item, type_arguments[0])
            return

        if origin in (dict, Mapping):
            if (
                not isinstance(value, dict)
                or len(type_arguments) != 2
                or type_arguments[0] is not str
            ):
                raise TypeError("Expected a string-keyed mapping.")
            for item in value.values():
                self._validate_value(item, type_arguments[1])
            return

        if (
            isinstance(expected_type, type)
            and issubclass(expected_type, Serializable)
        ):
            if _is_reference(value):
                self._validate_reference(value, expected_type)
            else:
                if not isinstance(value, dict):
                    raise TypeError("Expected an inline record or $ref.")
                self._validate_record(value, expected_type)
            return

        if isinstance(expected_type, type) and is_dataclass(expected_type):
            if not isinstance(value, dict):
                raise TypeError("Expected a dataclass mapping.")
            field_types = get_type_hints(expected_type)
            for field in fields(expected_type):
                if field.init and field.name in value:
                    self._validate_value(
                        value[field.name],
                        field_types.get(field.name, Any),
                    )
            return

        raise TypeError(
            f"Cannot validate values annotated as {expected_type!r}."
        )

    def _validate_reference(
        self,
        reference: Any,
        expected_type: type[Serializable],
    ) -> None:
        key = _reference_key(reference)
        try:
            record = self._records[key]
        except KeyError as error:
            raise ValueError(
                f"Unknown Serializable graph reference {_object_pointer(key)!r}."
            ) from error

        actual_type = expected_type._resolve_serialized_class(
            record.get("__module__"),
            record.get("__class__"),
        )
        class_name = actual_type.__name__
        index = key.removeprefix(f"{class_name}-")
        if key != class_name and not (
            key.startswith(f"{class_name}-") and index.isdigit()
        ):
            raise ValueError(
                f"Object key {key!r} does not identify its "
                f"{class_name} record."
            )
        if key in self._active:
            raise _GraphCycleError(
                "Cyclic Serializable graph references are not supported."
            )
        if key in self._visited:
            return

        self._active.add(key)
        try:
            self._validate_record(record, expected_type)
        finally:
            self._active.remove(key)
        self._visited.add(key)

    def _validate_record(
        self,
        record: dict[str, Any],
        expected_type: type[Serializable],
    ) -> None:
        actual_type = expected_type._resolve_serialized_class(
            record.get("__module__"),
            record.get("__class__"),
        )
        for field_name, field_type in actual_type._serialized_field_types().items():
            if field_name in record:
                self._validate_value(record[field_name], field_type)


class _GraphDecoder:
    """Resolve typed references from a flat Serializable object table."""

    def __init__(self, data: Mapping[str, Any]) -> None:
        _validate_graph_envelope(data)
        objects = data["objects"]
        assert isinstance(objects, dict)
        self.root = data["root"]
        self._records = cast(dict[str, dict[str, Any]], objects)
        self._instances: dict[str, Serializable] = {}
        self._active: set[str] = set()

    def decode(self, expected_type: Any) -> Any:
        return Serializable._deserialize_value(
            self.root,
            expected_type,
            graph=self,
        )

    def resolve(
        self,
        reference: Any,
        expected_type: type[Serializable],
    ) -> Serializable:
        key = _reference_key(reference)
        existing = self._instances.get(key)
        if existing is not None:
            if not isinstance(existing, expected_type):
                raise TypeError(
                    f"Reference {_object_pointer(key)!r} resolves to "
                    f"{type(existing).__name__}, expected {expected_type.__name__}."
                )
            return existing
        if key in self._active:
            raise _GraphCycleError(
                "Cyclic Serializable graph references are not supported."
            )

        record = self._records[key]
        self._active.add(key)
        try:
            instance = expected_type._from_record(record, graph=self)
        finally:
            self._active.remove(key)
        if not isinstance(instance, expected_type):
            raise TypeError(
                f"Reference {_object_pointer(key)!r} resolves to "
                f"{type(instance).__name__}, expected {expected_type.__name__}."
            )
        self._instances[key] = instance
        return instance


def _serialize_graph(value: Any) -> dict[str, Any]:
    """Serialize a complete value using one flat Serializable object table."""
    return _GraphEncoder().encode(value)


def _validate_graph(data: Mapping[str, Any], expected_type: Any) -> None:
    """Validate graph references and types without constructing objects."""
    _GraphValidator(data).validate(expected_type)


def _deserialize_graph(data: Mapping[str, Any], expected_type: Any) -> Any:
    """Deserialize a validated graph and preserve shared object references."""
    return _GraphDecoder(data).decode(expected_type)


def _validate_graph_envelope(data: Mapping[str, Any]) -> None:
    if not isinstance(data, Mapping):
        raise TypeError("A Serializable graph document must be a mapping.")
    if set(data) != {"root", "objects"}:
        raise ValueError(
            "A Serializable graph document requires exactly root and objects."
        )
    if not isinstance(data["objects"], dict):
        raise TypeError("Serializable graph objects must be a mapping.")


def _is_reference(value: Any) -> bool:
    return isinstance(value, dict) and set(value) == {_REFERENCE_KEY}


def _reference_key(reference: Any) -> str:
    if not _is_reference(reference):
        raise TypeError("A Serializable graph reference must contain only $ref.")
    pointer = reference[_REFERENCE_KEY]
    if type(pointer) is not str or not pointer.startswith(_OBJECT_POINTER_PREFIX):
        raise ValueError(f"Invalid Serializable graph reference {pointer!r}.")
    key = pointer.removeprefix(_OBJECT_POINTER_PREFIX)
    if not key or "/" in key or "~" in key:
        raise ValueError(f"Invalid Serializable graph reference {pointer!r}.")
    return key


def _object_pointer(key: str) -> str:
    return f"{_OBJECT_POINTER_PREFIX}{key}"
