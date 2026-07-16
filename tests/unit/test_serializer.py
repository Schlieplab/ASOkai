#!/usr/bin/env python
"""
Unit tests for the Serializable base class.
"""
import pytest
import json
from Bio.Seq import Seq
from ASOkai.Utils import Serializable


class SimpleSerializable(Serializable):
    """Simple test class for serialization."""
    
    def __init__(self, name: str, value: int, **kwargs):
        self.name = name
        self.value = value
        super().__init__(**kwargs)


class SerializableWithExclusions(Serializable):
    """Test class with excluded attributes."""
    
    _non_serializable_attrs = {'private_data', 'cache'}
    
    def __init__(
        self,
        public: str,
        private_data: str | None = None,
        cache: dict | None = None,
        **kwargs,
    ):
        self.public = public
        self.private_data = private_data
        self.cache = cache
        super().__init__(**kwargs)


class SerializableWithMapping(Serializable):
    """Test class with attribute name mapping."""
    
    def __init__(self, sequence: Seq, **kwargs):
        self._sequence = sequence
        super().__init__(**kwargs)
    

@pytest.mark.unit
@pytest.mark.serialization
class TestSerializableBasics:
    """Test basic serialization/deserialization."""
    
    def test_to_dict_basic(self):
        """Test basic to_dict conversion."""
        obj = SimpleSerializable(name="test", value=42)
        data = obj.to_dict()
        
        assert data['__class__'] == 'SimpleSerializable'
        assert data['__module__'] == 'tests.unit.test_serializer'
        assert data['name'] == 'test'
        assert data['value'] == 42
        
    def test_from_dict_basic(self):
        """Test basic from_dict reconstruction."""
        data = {
            '__class__': 'SimpleSerializable',
            '__module__': 'tests.unit.test_serializer',
            'name': 'test',
            'value': 42
        }
        
        obj = SimpleSerializable.from_dict(data)
        
        assert isinstance(obj, SimpleSerializable)
        assert obj.name == 'test'
        assert obj.value == 42
        
    def test_roundtrip_basic(self):
        """Test serialization -> deserialization roundtrip."""
        original = SimpleSerializable(name="test", value=42)
        data = original.to_dict()
        reconstructed = SimpleSerializable.from_dict(data)
        
        assert reconstructed.name == original.name
        assert reconstructed.value == original.value


@pytest.mark.unit
@pytest.mark.serialization
class TestSerializableExclusions:
    """Test _non_serializable_attrs functionality."""
    
    def test_excluded_attrs_not_serialized(self):
        """Test that excluded attributes are not in serialized data."""
        obj = SerializableWithExclusions(
            public="visible",
            private_data="secret",
            cache={"key": "value"}
        )
        data = obj.to_dict()
        
        assert 'public' in data
        assert 'private_data' not in data
        assert 'cache' not in data
        
    def test_excluded_attrs_dont_break_deserialization(self):
        """Test that missing excluded attrs don't break deserialization."""
        data = {
            '__class__': 'SerializableWithExclusions',
            '__module__': 'tests.unit.test_serializer',
            'public': 'visible'
        }
        
        # Should not raise, even though private_data and cache are missing
        obj = SerializableWithExclusions.from_dict(data)
        assert obj.public == 'visible'


@pytest.mark.unit
@pytest.mark.serialization
class TestSerializableNameMapping:
    """Test attribute name mapping functionality."""
    
    def test_name_mapping_serialization(self, sample_sequence):
        """Test that mapped names are serialized via registered adapter."""
        obj = SerializableWithMapping(sequence=sample_sequence)
        data = obj.to_dict()
        
        # _sequence is stored as a plain string under the public key "sequence"
        assert 'sequence' in data
        assert data['sequence'] == str(sample_sequence)
        assert '_sequence' not in data
        
    def test_name_mapping_deserialization(self, sample_sequence):
        """Test that mapped names are deserialized correctly via adapter."""
        data = {
            '__class__': 'SerializableWithMapping',
            '__module__': 'tests.unit.test_serializer',
            'sequence': str(sample_sequence),
        }
        
        obj = SerializableWithMapping.from_dict(data)
        
        assert hasattr(obj, '_sequence')
        assert isinstance(obj._sequence, Seq)
        assert str(obj._sequence) == str(sample_sequence)


@pytest.mark.unit
@pytest.mark.serialization
class TestSerializableFileOperations:
    """Test file I/O operations."""
    
    def test_to_file(self, temp_json_file):
        """Test writing to file."""
        obj = SimpleSerializable(name="test", value=42)
        obj.to_file(temp_json_file)
        
        # Verify file was created and contains valid JSON
        with open(temp_json_file, 'r') as f:
            data = json.load(f)
        
        assert data['name'] == 'test'
        assert data['value'] == 42
        
    def test_from_file(self, temp_json_file):
        """Test reading from file."""
        # Write test data
        obj = SimpleSerializable(name="test", value=42)
        obj.to_file(temp_json_file)
        
        # Read back
        reconstructed = SimpleSerializable.from_file(temp_json_file)
        
        assert isinstance(reconstructed, SimpleSerializable)
        assert reconstructed.name == 'test'
        assert reconstructed.value == 42
        
    def test_file_roundtrip(self, temp_json_file, sample_sequence):
        """Test complete file roundtrip."""
        original = SerializableWithMapping(sequence=sample_sequence)
        original.to_file(temp_json_file)
        
        reconstructed = SerializableWithMapping.from_file(temp_json_file)
        
        assert str(reconstructed._sequence) == str(original._sequence)


@pytest.mark.unit
@pytest.mark.serialization
class TestSerializableComplexTypes:
    """Test serialization of complex nested types."""
    
    def test_nested_dict_serialization(self):
        """Test serialization of nested dictionaries."""
        obj = SimpleSerializable(name="test", value=42)
        setattr(obj, "data", {"nested": {"key": "value"}})
        
        data = obj.to_dict()
        
        assert data['data']['nested']['key'] == 'value'
        
    def test_list_serialization(self):
        """Test serialization of lists."""
        obj = SimpleSerializable(name="test", value=42)
        setattr(obj, "items", [1, 2, 3, "four"])
        
        data = obj.to_dict()
        
        assert data['items'] == [1, 2, 3, "four"]
        
    def test_registered_type_in_dict(self, sample_sequence):
        """External types in nested dicts are not supported by default."""
        obj = SimpleSerializable(name="test", value=42)
        setattr(obj, "sequences", {"seq1": sample_sequence})
        
        with pytest.raises(TypeError, match="Cannot serialize type Seq"):
            obj.to_dict()
