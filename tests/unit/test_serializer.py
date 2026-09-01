#!/usr/bin/env python
"""
Filename: tests/unit/test_serializer.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Version: 0.1.1
Description: Unit tests for the Serializable base class.
License: LGPL-3.0-or-later
"""

import pytest
from dataclasses import dataclass

from Bio.Seq import Seq

from ASOkai.Utils import Serializable
from ASOkai.Plugins import JsonFile
from ASOkai._pipeline.contracts.json_schema import build_json_schema


@dataclass(frozen=True)
class ExternalLocation:
    """Test value type that does not depend on Serializable."""

    reference_id: str
    start: int
    end: int


class SimpleSerializable(Serializable):
    """Simple test class for serialization."""

    name: str
    value: int

    def __init__(self, name: str, value: int, **kwargs):
        self.name = name
        self.value = value
        super().__init__(**kwargs)


class SerializableWithExclusions(Serializable):
    """Test class with excluded attributes."""

    public: str
    private_data: str | None
    cache: dict | None
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

    _sequence: Seq
    _serialized_names = {"_sequence": "sequence"}

    def __init__(self, sequence: Seq, **kwargs):
        self._sequence = sequence
        super().__init__(**kwargs)


class SerializableWithLocations(Serializable):
    """Test class containing external dataclass values."""

    locations: list[ExternalLocation]

    def __init__(self, locations):
        self.locations = locations
        super().__init__()


class SerializableWithSequences(Serializable):
    """Test class containing sequence values inside a mapping."""

    sequences: dict[str, Seq]

    def __init__(self, sequences: dict[str, Seq]):
        self.sequences = sequences
        super().__init__()


class SerializableWithOptionalSequence(Serializable):
    """Test class containing a union-supported optional sequence."""

    sequence: Seq | None

    def __init__(self, sequence: Seq | None):
        self.sequence = sequence
        super().__init__()


class NestedItem(Serializable):
    """Serializable value nested inside declared containers."""

    value: int

    def __init__(self, value: int):
        self.value = value
        super().__init__()


class SerializableWithNestedItems(Serializable):
    """Serializable containing nested mappings and lists."""

    groups: dict[str, list[NestedItem]]

    def __init__(self, groups: dict[str, list[NestedItem]]):
        self.groups = groups
        super().__init__()


class ClosedSerializable(Serializable):
    """Serializable whose constructor does not accept extra fields."""

    value: int

    def __init__(self, value: int):
        self.value = value
        super().__init__()


class UnsupportedValue:
    """Value without a supported serialized representation."""


class SerializableWithUnsupportedValue(Serializable):
    """Serializable with an unsupported declared field type."""

    value: UnsupportedValue

    def __init__(self, value: UnsupportedValue):
        self.value = value
        super().__init__()


class SerializableWithTuple(Serializable):
    """Serializable used to verify that tuples are not silently coerced."""

    values: tuple[int, ...]

    def __init__(self, values: tuple[int, ...]):
        self.values = values
        super().__init__()


@pytest.mark.unit
@pytest.mark.serialization
class TestSerializableBasics:
    """Test basic serialization/deserialization."""

    def test_basic_shape_and_roundtrip(self):
        original = SimpleSerializable(name="test", value=42)
        data = original.to_dict()
        reconstructed = SimpleSerializable.from_dict(data)

        assert data == {
            '__class__': 'SimpleSerializable',
            '__module__': 'tests.unit.test_serializer',
            'name': 'test',
            'value': 42,
        }
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

    def test_name_mapping_roundtrip(self, sample_sequence):
        obj = SerializableWithMapping(sequence=sample_sequence)
        data = obj.to_dict()
        obj = SerializableWithMapping.from_dict(data)

        assert data['sequence'] == str(sample_sequence)
        assert '_sequence' not in data
        assert hasattr(obj, '_sequence')
        assert isinstance(obj._sequence, Seq)
        assert str(obj._sequence) == str(sample_sequence)

    def test_name_mapping_does_not_bypass_the_declared_type(self):
        data = SerializableWithMapping(sequence=Seq("ACGT")).to_dict()
        data["sequence"] = 4

        with pytest.raises(TypeError, match="Seq values must be serialized"):
            SerializableWithMapping.from_dict(data)


@pytest.mark.unit
@pytest.mark.serialization
class TestSerializableComplexTypes:
    """Test serialization of complex nested types."""

    def test_nested_serializable_values_roundtrip(self):
        original = SerializableWithNestedItems(
            groups={"first": [NestedItem(1), NestedItem(2)]},
        )
        contract = JsonFile(SerializableWithNestedItems)

        reconstructed = contract.loads(contract.dumps(original))

        assert [item.value for item in reconstructed.groups["first"]] == [1, 2]
        assert all(
            isinstance(item, NestedItem)
            for item in reconstructed.groups["first"]
        )

    def test_sequence_values_roundtrip_inside_annotated_mapping(
        self,
        sample_sequence,
    ):
        original = SerializableWithSequences(
            sequences={"seq1": sample_sequence},
        )

        contract = JsonFile(SerializableWithSequences)
        serialized = original.to_dict()
        reconstructed = contract.loads(contract.dumps(original))

        assert serialized["sequences"] == {"seq1": str(sample_sequence)}
        assert reconstructed.sequences == {"seq1": sample_sequence}

    @pytest.mark.parametrize("sequence", [Seq("ACGT"), None])
    def test_optional_sequence_roundtrips_through_its_json_contract(
        self,
        sequence,
    ):
        contract = JsonFile(SerializableWithOptionalSequence)

        reconstructed = contract.loads(
            contract.dumps(SerializableWithOptionalSequence(sequence)),
        )

        assert reconstructed.sequence == sequence

    def test_sequence_mapping_annotation_produces_matching_schema(self):
        schema = build_json_schema(SerializableWithSequences)

        assert schema["properties"]["sequences"] == {
            "type": "object",
            "additionalProperties": {
                "type": "string",
                "examples": ["A"],
            },
        }

    def test_dataclass_values_roundtrip_from_class_annotations(self):
        original = SerializableWithLocations(
            locations=[ExternalLocation("reference-1", 10, 20)]
        )
        contract = JsonFile(SerializableWithLocations)

        serialized = original.to_dict()
        reconstructed = contract.loads(contract.dumps(original))

        assert serialized["locations"] == [
            {
                "reference_id": "reference-1",
                "start": 10,
                "end": 20,
            }
        ]
        assert reconstructed.locations == original.locations

    def test_dataclass_annotations_produce_recursive_json_schema(self):
        schema = build_json_schema(SerializableWithLocations)

        assert schema["properties"]["locations"] == {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["reference_id", "start", "end"],
                "properties": {
                    "reference_id": {"type": "string"},
                    "start": {"type": "integer"},
                    "end": {"type": "integer"},
                },
            },
        }


@pytest.mark.unit
@pytest.mark.serialization
class TestSerializableInputValidation:
    """Test strict handling of serialized input boundaries."""

    def test_unexpected_field_is_rejected_without_kwargs(self):
        data = ClosedSerializable(1).to_dict()
        data["unexpected"] = 2

        with pytest.raises(ValueError, match="Unexpected serialized field"):
            ClosedSerializable.from_dict(data)

    def test_extra_metadata_kwargs_roundtrip(self):
        original = SimpleSerializable(
            name="test",
            value=42,
            metadata={
                "source": "external",
                "tags": ["reviewed", "imported"],
                "details": {"priority": 1},
            },
        )

        reconstructed = SimpleSerializable.from_dict(original.to_dict())

        assert getattr(reconstructed, "metadata") == {
            "source": "external",
            "tags": ["reviewed", "imported"],
            "details": {"priority": 1},
        }

    def test_unknown_implementation_is_rejected_without_importing_it(self):
        data = SimpleSerializable(name="test", value=42).to_dict()
        data["__module__"] = "package_that_is_not_installed"

        with pytest.raises(ValueError, match="Unknown SimpleSerializable"):
            SimpleSerializable.from_dict(data)

    def test_unsupported_declared_type_is_rejected(self):
        data = {
            "__class__": "SerializableWithUnsupportedValue",
            "__module__": "tests.unit.test_serializer",
            "value": "unsupported",
        }

        with pytest.raises(TypeError, match="Cannot deserialize values annotated"):
            SerializableWithUnsupportedValue.from_dict(data)

    def test_tuple_values_are_rejected_instead_of_coerced_to_lists(self):
        value = SerializableWithTuple((1, 2))

        with pytest.raises(TypeError, match="Cannot serialize type tuple"):
            value.to_dict()
