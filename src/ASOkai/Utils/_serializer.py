#!/usr/bin/env python
"""
Filename: src/ASOkai/Utils/serializer.py
Author: Arash Ayat
Copyright: 2025, Alexander Schliep
Version: 0.1.0
Description: This file defines the Serializable class for serializing and deserializing objects.
License: LGPL-3.0-or-later
"""
from typing import Dict, Any, Type, TypeVar, Callable, Optional
import json
import importlib
import inspect

T = TypeVar('T', bound='Serializable')


class Serializable:
    """
    Base class for objects that can be serialized to a dictionary and file.
    """
    
    # Class-level registry for external types
    # Maps *internal instance attribute name* -> (serialized_key, serialize_func, flatten)
    _attribute_serializers: Dict[str, tuple[str, Callable[[Any], Any], bool]] = {}
    # Maps *__init__ parameter / incoming key name* -> (init_arg_name, deserialize_func)
    _attribute_deserializers: Dict[str, tuple[str, Callable[[Any], Any]]] = {}
    
    # Attributes to exclude from serialization
    _non_serializable_attrs: set[str] = set()
    

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
        if attribute_name in self._attribute_serializers:
            serialize_attribute_name, serialize_func, flatten = self._attribute_serializers[attribute_name]
            if flatten:
                return serialize_func(value)
            else:
                return {serialize_attribute_name: serialize_func(value)}
        return {attribute_name: self._serialize_value(value)}


    def _serialize_value(self, value: Any) -> Any:
        """
        Default method to serialize a value to a dictionary.
        """
        if isinstance(value, (str, int, float, bool, type(None))):
            return value
        elif isinstance(value, Serializable):
            return value.to_dict()
        elif isinstance(value, dict):
            return {k: self._serialize_value(v) for k, v in value.items()}
        elif isinstance(value, (list, tuple)):
            return [self._serialize_value(item) for item in value]
        else:
            raise TypeError(f"Cannot serialize type {type(value).__name__}")

    def to_file(self, file_path: str) -> None:
        """
        method to write the object to a file.
        """
        with open(file_path, 'w') as f:
            json.dump(self.to_dict(), f, indent=4)

    @classmethod
    def _deserialize_value(cls, value_data: Any) -> Any:
        """
        Default method to deserialize a value from a dictionary.
        """
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
    def _deserialize_attribute(cls, attribute_name: str, value: Any) -> Any:
        """
        Deserialize an attribute from a dictionary.
        """
        if attribute_name in cls._attribute_deserializers:
            deserialize_attribute_name, deserialize_func = cls._attribute_deserializers[attribute_name]
            return {deserialize_attribute_name: deserialize_func(value)}

        return {attribute_name: cls._deserialize_value(value)}

    @classmethod
    def from_dict(cls: Type[T], data: Dict[str, Any]) -> T:
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
        init_args: Dict[str, Any] = {}


        for param_name in sig.parameters:
            if param_name in data:
                value = data.pop(param_name)
                init_args.update(cls._deserialize_attribute(param_name, value))

        # Pass any leftover data as kwargs, if __init__ accepts them
        for param in sig.parameters.values():
            if param.kind == param.VAR_KEYWORD:
                deserialized_kwargs = {k: cls._deserialize_value(v) for k, v in data.items()}
                init_args.update(deserialized_kwargs)
                break

        return cls_from_data(**init_args)


    @classmethod
    def from_file(cls: Type[T], file_path: str) -> T:
        """
        Create an object from a JSON file.
        """
        with open(file_path, 'r') as f:
            data = json.load(f)
        return cls.from_dict(data)
