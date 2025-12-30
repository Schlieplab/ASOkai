#!/usr/bin/env python
"""
Filename: src/ASOkai/utils/serializer.py
Author: Arash Ayat
Copyright: 2025, Alexander Schliep
Version: 0.1.0
Description: This file defines the Serializable class for serializing and deserializing objects.
License: LGPL-3.0-or-later
"""
from typing import Dict, Any, Type, TypeVar
import json
import importlib
import inspect

T = TypeVar('T', bound='Serializable')

class Serializable:
    """
    Base class for objects that can be serialized to a dictionary and file.
    """
    def to_dict(self) -> Dict:
        """
        method to convert the object to a dictionary.
        """
        data = {
            '__class__': self.__class__.__name__,
            '__module__': self.__class__.__module__
        }
        
        for key, value in self.__dict__.items():
            data.update(self._serialize_attribute(key, value))
            
        return data

    def _serialize_attribute(self, key: str, value: Any) -> Dict[str, Any]:
        return {key: self._serialize_value(value)}

    def _serialize_value(self, value: Any) -> Any:
        if isinstance(value, (str, int, float, bool, type(None))):
            return value
        elif isinstance(value, Serializable):
            return value.to_dict()
        elif isinstance(value, dict):
            return {k: self._serialize_value(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [self._serialize_value(item) for item in value]
        else:
            return str(value)

    def to_file(self, file_path: str) -> None:
        """
        method to write the object to a file.
        """
        with open(file_path, 'w') as f:
            json.dump(self.to_dict(), f, indent=4)

    @classmethod
    def _get_init_arg_name_map(cls) -> Dict[str, str]:
        """
        Provides a mapping from serialized attribute names to __init__ parameter names.
        Override this in a subclass if the names differ.
        Example: return {"_sequence": "sequence"}
        """
        return {}

    @classmethod
    def _deserialize_value(cls, value_data: Any) -> Any:
        """
        Hook for subclasses to deserialize special value types.
        The base implementation handles other Serializable objects, dicts, and lists.
        """
        if isinstance(value_data, list):
            return [cls._deserialize_value(item) for item in value_data]
        elif isinstance(value_data, dict):
            if '__class__' in value_data and '__module__' in value_data:
                return Serializable.from_dict(value_data)
            else:
                return {k: cls._deserialize_value(v) for k, v in value_data.items()}
        return value_data

    @classmethod
    def from_dict(cls: Type[T], data: Dict) -> T:
        """
        Create an object from a dictionary using introspection.
        """
        if isinstance(data, dict) and '__class__' in data and '__module__' in data:
            module_name = data.pop('__module__')
            class_name = data.pop('__class__')
            module = importlib.import_module(module_name)
            cls_from_data = getattr(module, class_name)

            if not issubclass(cls_from_data, cls):
                raise TypeError(f"Data is for class {class_name}, which is not a subclass of {cls.__name__}")

            if issubclass(cls_from_data, Serializable):
                sig = inspect.signature(cls_from_data.__init__)
                name_map = cls_from_data._get_init_arg_name_map()
                
                init_args = {}

                # First, handle mapped arguments
                for attr_name, param_name in name_map.items():
                    if attr_name in data and param_name in sig.parameters:
                        value = data.pop(attr_name)
                        init_args[param_name] = cls_from_data._deserialize_value(value)

                # Handle remaining arguments where attr_name == param_name
                for param_name in sig.parameters:
                    if param_name in data:
                         value = data.pop(param_name)
                         init_args[param_name] = cls_from_data._deserialize_value(value)

                # Pass any leftover data as kwargs, if __init__ accepts them
                for param in sig.parameters.values():
                    if param.kind == param.VAR_KEYWORD:
                        # Deserialize remaining data for kwargs
                        deserialized_kwargs = {k: cls_from_data._deserialize_value(v) for k, v in data.items()}
                        init_args.update(deserialized_kwargs)
                        break

                return cls_from_data(**init_args)

        raise ValueError("Data is not a valid serialized object dictionary.")


    @classmethod
    def from_file(cls: Type[T], file_path: str) -> T:
        """
        Create an object from a JSON file.
        """
        with open(file_path, 'r') as f:
            data = json.load(f)
        return cls.from_dict(data)
