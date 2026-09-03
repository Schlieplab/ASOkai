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
from collections.abc import Iterable, Mapping
from dataclasses import fields, is_dataclass
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


class Serializable:
    """
    Base class for objects that can be serialized to a dictionary.
    """
    
    _serialized_names: ClassVar[dict[str, str]] = {}
    _flattened_attributes: ClassVar[frozenset[str]] = frozenset()
    _non_serializable_attrs: ClassVar[set[str]] = set()

    @classmethod
    def _inherited_serialized_names(cls) -> dict[str, str]:
        """Return attribute-to-document names declared across the hierarchy."""
        serialized_names: dict[str, str] = {}
        for base in reversed(cls.__mro__):
            serialized_names.update(
                base.__dict__.get("_serialized_names", {})
            )
        return serialized_names

    @classmethod
    def _inherited_flattened_attributes(cls) -> frozenset[str]:
        """Return flattened attribute names declared across the hierarchy."""
        flattened_attributes: set[str] = set()
        for base in reversed(cls.__mro__):
            flattened_attributes.update(
                base.__dict__.get("_flattened_attributes", frozenset())
            )
        return frozenset(flattened_attributes)

    @classmethod
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
    def _constructor_parameters(
        cls,
    ) -> Mapping[str, inspect.Parameter]:
        """Return the parameters accepted by this type's constructor."""
        return inspect.signature(cls.__init__).parameters

    @classmethod
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
        """ 
        Convert the object to a dictionary.
        """
        data: dict[str, Any] = {
            '__class__': self.__class__.__name__,
            '__module__': self.__class__.__module__
        }
        for key, value in self.__dict__.items():
            data.update(self._serialize_attribute(key, value))
        return data
    
    def _serialize_attribute(
        self,
        attribute_name: str,
        value: Any,
    ) -> dict[str, Any]:
        """
        Serialize an attribute to a dictionary.
        """
        if attribute_name in self._non_serializable_attrs:
            return {}
        if attribute_name in type(self)._inherited_flattened_attributes():
            serialized_value = self._serialize_value(value)
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
        return {serialized_name: self._serialize_value(value)}


    def _serialize_value(self, value: Any) -> Any:
        """
        Default method to serialize a value to a dictionary.
        """
        if isinstance(value, Seq):
            return str(value)
        elif _is_scalar(value):
            return value
        elif isinstance(value, Serializable):
            return value.to_dict()
        elif is_dataclass(value) and not isinstance(value, type):
            return {
                field.name: self._serialize_value(getattr(value, field.name))
                for field in fields(value)
                if field.init
            }
        elif isinstance(value, dict):
            if any(type(key) is not str for key in value):
                raise TypeError("Serialized mappings must have string keys.")
            return {k: self._serialize_value(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [self._serialize_value(item) for item in value]
        else:
            raise TypeError(f"Cannot serialize type {type(value).__name__}")

    @classmethod
    def _deserialize_value(
        cls,
        value_data: Any,
        expected_type: Any = Any,
    ) -> Any:
        """
        Default method to deserialize a value from a dictionary.
        """
        if expected_type is Any:
            if isinstance(value_data, list):
                return [cls._deserialize_value(item) for item in value_data]
            if isinstance(value_data, dict):
                if '__type__' in value_data:
                    raise ValueError(
                        "Legacy serialized payloads using '__type__' are not "
                        "supported."
                    )
                if '__class__' in value_data and '__module__' in value_data:
                    return Serializable.from_dict(value_data)
                return {
                    key: cls._deserialize_value(value)
                    for key, value in value_data.items()
                }
            return value_data

        origin = get_origin(expected_type)
        type_arguments = get_args(expected_type)

        if origin in (Union, UnionType):
            errors: list[TypeError | ValueError] = []
            for alternative in type_arguments:
                try:
                    return cls._deserialize_value(value_data, alternative)
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
                cls._deserialize_value(item, item_type)
                for item in value_data
            ]

        if origin in (dict, Mapping):
            if not isinstance(value_data, dict):
                raise TypeError("Expected a mapping.")
            if len(type_arguments) != 2 or type_arguments[0] is not str:
                raise TypeError("Serialized mappings must have string keys.")
            value_type = type_arguments[1]
            return {
                cls._deserialize_value(key, str): cls._deserialize_value(
                    value,
                    value_type,
                )
                for key, value in value_data.items()
            }

        if (
            isinstance(expected_type, type)
            and issubclass(expected_type, Serializable)
        ):
            if not isinstance(value_data, dict):
                raise TypeError("Expected a serialized object mapping.")
            return expected_type.from_dict(value_data)

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
        if not (isinstance(data, dict) and '__class__' in data and '__module__' in data):
            raise ValueError("Data is not a valid serialized object dictionary.")

        data = data.copy()
        module_name = data.pop('__module__')
        class_name = data.pop('__class__')
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
                    value
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
            )

        return cast(Self, cls_from_data(**init_args))

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
