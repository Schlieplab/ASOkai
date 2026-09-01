#!/usr/bin/env python
"""
Filename: src/ASOkai/Utils/_serializer.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Version: 0.1.1
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
    Callable,
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
    
    # Class-level registry for external types
    # Maps *internal instance attribute name* -> (serialized_key, serialize_func, flatten)
    _attribute_serializers: dict[
        str,
        tuple[str, Callable[[Any], Any], bool],
    ] = {}
    # Maps *__init__ parameter / incoming key name* -> (init_arg_name, deserialize_func)
    _attribute_deserializers: dict[
        str,
        tuple[str, Callable[[Any], Any]],
    ] = {}
    
    # Attributes to exclude from serialization
    _non_serializable_attrs: set[str] = set()

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Give each subclass its own attribute-adapter declarations."""
        super().__init_subclass__(**kwargs)
        cls._attribute_serializers = {}
        cls._attribute_deserializers = {}

    @classmethod
    def _registered_attribute_serializers(
        cls,
    ) -> dict[str, tuple[str, Callable[[Any], Any], bool]]:
        """Return inherited serializers without sharing mutable registries."""
        serializers: dict[
            str,
            tuple[str, Callable[[Any], Any], bool],
        ] = {}
        for base in reversed(cls.__mro__):
            serializers.update(
                base.__dict__.get("_attribute_serializers", {})
            )
        return serializers

    @classmethod
    def _registered_attribute_deserializers(
        cls,
    ) -> dict[str, tuple[str, Callable[[Any], Any]]]:
        """Return inherited deserializers without sharing mutable registries."""
        deserializers: dict[
            str,
            tuple[str, Callable[[Any], Any]],
        ] = {}
        for base in reversed(cls.__mro__):
            deserializers.update(
                base.__dict__.get("_attribute_deserializers", {})
            )
        return deserializers
    

    @classmethod
    def _serialized_field_types(cls) -> dict[str, Any]:
        """Return serialized field names and their declared Python types."""
        serialized_fields: dict[str, Any] = {}
        attribute_serializers = cls._registered_attribute_serializers()
        serialized_private_fields = attribute_serializers.keys()

        for class_in_hierarchy in reversed(cls.__mro__):
            declared_fields = _declared_field_types(
                class_in_hierarchy,
                serialized_private_fields=serialized_private_fields,
            )
            for field_name, field_type in declared_fields.items():
                if field_name in cls._non_serializable_attrs:
                    continue

                serializer = attribute_serializers.get(field_name)
                if serializer is None:
                    serialized_fields[field_name] = field_type
                    continue

                serialized_name, _, flatten = serializer
                if not flatten:
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

    def __init__(self, **kwargs: Scalar) -> None:
        """
        Initialize with keyword arguments.
        Extra scalar values are retained as instance attributes.
        """
        for key, value in kwargs.items():
            if not _is_scalar(value):
                raise TypeError(
                    f"Extra Serializable attribute {key!r} must be a scalar; "
                    f"received {type(value).__name__}."
                )
            setattr(self, key, value)

    @classmethod
    def register_attribute(
        cls,
        attribute_name: str,
        serialized_attribute_name: str | None = None,
        deserialized_attribute_name: str | None = None,
        serialize: Callable[[Any], Any] | None = None,
        deserialize: Callable[[Any], Any] | None = None,
        flatten: bool = False) -> None:
        """
        Register an external attribute for serialization/deserialization.
        
        Args:
            attribute_name: The name of the attribute to register.
            serialized_attribute_name: The name of the attribute to use for serialization.
            deserialized_attribute_name: The name of the attribute to use for deserialization.
            serialize: A function that takes an instance and returns the value of the attribute.
            deserialize: A function that takes a value and returns the instance.
            flatten: If True, the attribute is serialized as a top-level key instead of a nested dict.
        """
        if serialized_attribute_name is None:
            serialized_attribute_name = attribute_name
        if deserialized_attribute_name is None:
            deserialized_attribute_name = serialized_attribute_name

        if serialize is not None:
            cls._attribute_serializers[attribute_name] = (serialized_attribute_name, serialize, flatten)
        if deserialize is not None:
            cls._attribute_deserializers[serialized_attribute_name] = (deserialized_attribute_name, deserialize)

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
        serializers = type(self)._registered_attribute_serializers()
        if attribute_name in serializers:
            serialize_attribute_name, serialize_func, flatten = serializers[attribute_name]
            if flatten:
                return serialize_func(value)
            else:
                return {serialize_attribute_name: serialize_func(value)}
        return {attribute_name: self._serialize_value(value)}


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

        if (
            isinstance(expected_type, type)
            and issubclass(expected_type, Serializable)
        ):
            if not isinstance(value_data, dict):
                raise TypeError("Expected a serialized object mapping.")
            return expected_type.from_dict(value_data)

        raise TypeError(
            f"Cannot deserialize values annotated as {expected_type!r}."
        )

    @classmethod
    def _deserialize_attribute(
        cls,
        attribute_name: str,
        value: Any,
        expected_type: Any = Any,
    ) -> Any:
        """
        Deserialize an attribute from a dictionary.
        """
        deserializers = cls._registered_attribute_deserializers()
        if attribute_name in deserializers:
            deserialize_attribute_name, deserialize_func = deserializers[attribute_name]
            deserialized_value = (
                deserialize_func(value)
                if expected_type is Any
                else cls._deserialize_value(value, expected_type)
            )
            return {deserialize_attribute_name: deserialized_value}

        return {
            attribute_name: cls._deserialize_value(value, expected_type)
        }

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

        sig = inspect.signature(cls_from_data.__init__)
        constructor_parameters = sig.parameters
        accepts_extra_scalars = any(
            parameter.kind is inspect.Parameter.VAR_KEYWORD
            for parameter in constructor_parameters.values()
        )
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
                if not accepts_extra_scalars:
                    raise ValueError(
                        f"Unexpected serialized field {serialized_name!r} for "
                        f"{cls_from_data.__name__}."
                    )
                if not _is_scalar(value):
                    raise TypeError(
                        f"Extra serialized field {serialized_name!r} must be "
                        f"a scalar; received {type(value).__name__}."
                    )
                init_args[serialized_name] = value
                continue

            decoded_attributes = cls_from_data._deserialize_attribute(
                serialized_name,
                value,
                serialized_field_types[serialized_name],
            )
            for constructor_name, decoded_value in decoded_attributes.items():
                parameter = constructor_parameters.get(constructor_name)
                if parameter is None and not accepts_extra_scalars:
                    raise ValueError(
                        f"Serialized field {serialized_name!r} does not map to "
                        f"a constructor argument of {cls_from_data.__name__}."
                    )
                if (
                    parameter is not None
                    and parameter.kind is inspect.Parameter.POSITIONAL_ONLY
                ):
                    raise TypeError(
                        f"Serializable constructor argument {constructor_name!r} "
                        "cannot be positional-only."
                    )
                if constructor_name in init_args:
                    raise ValueError(
                        f"Multiple serialized fields map to constructor argument "
                        f"{constructor_name!r}."
                    )
                init_args[constructor_name] = decoded_value

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

        candidates: list[type[Serializable]] = []
        pending = [cls]
        seen: set[type[Serializable]] = set()
        while pending:
            candidate = pending.pop()
            if candidate in seen:
                continue
            seen.add(candidate)
            candidates.append(candidate)
            pending.extend(candidate.__subclasses__())

        matches = [
            candidate
            for candidate in candidates
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
    """Return whether a value is supported as an extra serialized scalar."""
    return value is None or type(value) in (str, int, float, bool)
