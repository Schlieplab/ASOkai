#!/usr/bin/env python
"""
Filename: src/ASOkai/Utils/_serializer.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Version: 0.1.1
Description: This file defines the Serializable class for serializing and deserializing objects.
License: LGPL-3.0-or-later
"""
import importlib
import inspect
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from types import NoneType, UnionType
from typing import (
    Any,
    Callable,
    Dict,
    Literal,
    Optional,
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
    _attribute_serializers: Dict[str, tuple[str, Callable[[Any], Any], bool]] = {}
    # Maps *__init__ parameter / incoming key name* -> (init_arg_name, deserialize_func)
    _attribute_deserializers: Dict[str, tuple[str, Callable[[Any], Any]]] = {}
    
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
    ) -> Dict[str, tuple[str, Callable[[Any], Any], bool]]:
        """Return inherited serializers without sharing mutable registries."""
        serializers: Dict[str, tuple[str, Callable[[Any], Any], bool]] = {}
        for base in reversed(cls.__mro__):
            serializers.update(
                base.__dict__.get("_attribute_serializers", {})
            )
        return serializers

    @classmethod
    def _registered_attribute_deserializers(
        cls,
    ) -> Dict[str, tuple[str, Callable[[Any], Any]]]:
        """Return inherited deserializers without sharing mutable registries."""
        deserializers: Dict[str, tuple[str, Callable[[Any], Any]]] = {}
        for base in reversed(cls.__mro__):
            deserializers.update(
                base.__dict__.get("_attribute_deserializers", {})
            )
        return deserializers
    

    def __init__(self, **kwargs: Any) -> None:
        """
        Initialize with keyword arguments.
        All kwargs are set as instance attributes.
        """
        for key, value in kwargs.items():
            setattr(self, key, value)

    @classmethod
    def register_attribute(
        cls,
        attribute_name: str,
        serialized_attribute_name: Optional[str] = None,
        deserialized_attribute_name: Optional[str] = None,
        serialize: Optional[Callable[[Any], Any]] = None,
        deserialize: Optional[Callable[[Any], Any]] = None,
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

    def to_dict(self) -> Dict[str, Any]:
        """ 
        Convert the object to a dictionary.
        """
        data: Dict[str, Any] = {
            '__class__': self.__class__.__name__,
            '__module__': self.__class__.__module__
        }
        for key, value in self.__dict__.items():
            data.update(self._serialize_attribute(key, value))
        return data
    
    def _serialize_attribute(self, attribute_name: str, value: Any) -> Dict[str, Any]:
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
        elif isinstance(value, Scalar):
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
            return {k: self._serialize_value(v) for k, v in value.items()}
        elif isinstance(value, (list, tuple)):
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
            item_type = type_arguments[0] if type_arguments else Any
            return [
                cls._deserialize_value(item, item_type)
                for item in value_data
            ]

        if origin in (dict, Mapping):
            if not isinstance(value_data, dict):
                raise TypeError("Expected a mapping.")
            value_type = type_arguments[1] if len(type_arguments) == 2 else Any
            return {
                key: cls._deserialize_value(value, value_type)
                for key, value in value_data.items()
            }

        if isinstance(expected_type, type) and is_dataclass(expected_type):
            if not isinstance(value_data, dict):
                raise TypeError("Expected a dataclass mapping.")
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

        if isinstance(value_data, list):
            return [cls._deserialize_value(item) for item in value_data]
        elif isinstance(value_data, dict):
            # Explicitly reject legacy external-type markers.
            if '__type__' in value_data:
                raise ValueError(
                    "Legacy serialized payloads using '__type__' are not supported."
                )
            if '__class__' in value_data and '__module__' in value_data:
                return Serializable.from_dict(value_data)
            # Regular dict - recursively deserialize values
            return {k: cls._deserialize_value(v) for k, v in value_data.items()}
        return value_data

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
            if expected_type is not Any:
                try:
                    deserialized_value = cls._deserialize_value(
                        value,
                        expected_type,
                    )
                except (TypeError, ValueError):
                    deserialized_value = deserialize_func(value)
            else:
                deserialized_value = deserialize_func(value)
            return {deserialize_attribute_name: deserialized_value}

        return {
            attribute_name: cls._deserialize_value(value, expected_type)
        }

    @classmethod
    def from_dict(
        cls,
        data: Dict[str, Any],
    ) -> Self:
        """
        Create an object from a dictionary.
        """
        if not (isinstance(data, dict) and '__class__' in data and '__module__' in data):
            raise ValueError("Data is not a valid serialized object dictionary.")

        # Copy to avoid mutating the input
        data = data.copy()
        module_name = data.pop('__module__')
        class_name = data.pop('__class__')
        module = importlib.import_module(module_name)
        cls_from_data = getattr(module, class_name)

        if not issubclass(cls_from_data, Serializable):
            raise TypeError(f"Class {class_name} is not a subclass of Serializable")

        if not issubclass(cls_from_data, cls):
            raise TypeError(f"Data is for class {class_name}, which is not a subclass of {cls.__name__}")

        sig = inspect.signature(cls_from_data.__init__)
        constructor_types = get_type_hints(cls_from_data.__init__)
        init_args: Dict[str, Any] = {}


        for param_name in sig.parameters:
            if param_name in data:
                value = data.pop(param_name)
                init_args.update(
                    cls._deserialize_attribute(
                        param_name,
                        value,
                        constructor_types.get(param_name, Any),
                    )
                )

        # Pass any leftover data as kwargs, if __init__ accepts them
        for param in sig.parameters.values():
            if param.kind == param.VAR_KEYWORD:
                deserialized_kwargs = {k: cls._deserialize_value(v) for k, v in data.items()}
                init_args.update(deserialized_kwargs)
                break

        return cast(Self, cls_from_data(**init_args))
