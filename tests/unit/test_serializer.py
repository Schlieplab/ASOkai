#!/usr/bin/env python
"""
Filename: tests/unit/test_serializer.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Unit tests for the Serializable base class.
License: LGPL-3.0-or-later
"""

import json

import pytest
from dataclasses import dataclass
from typing import Any

from Bio.Seq import Seq

from ASOkai.Utils import Serializable
from ASOkai.Utils._serializer import (
    _deserialize_graph,
    _serialize_graph,
    _validate_graph,
)
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


@dataclass
class SerializableDataclass(Serializable):
    """Dataclass that retains the Serializable tagged representation."""

    value: int


class SerializableWithSerializableDataclass(Serializable):
    """Serializable containing another Serializable implemented as a dataclass."""

    item: SerializableDataclass

    def __init__(self, item: SerializableDataclass):
        self.item = item
        super().__init__()


class SerializableWithDefault(Serializable):
    """Serializable with a JSON-compatible constructor default."""

    label: str

    def __init__(self, label: str = "default"):
        self.label = label
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


class NestedItemSubtype(NestedItem):
    """Concrete subtype used to verify graph polymorphism."""


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


class SerializablePair(Serializable):
    """Two typed references used to verify graph identity."""

    first: NestedItem
    second: NestedItem

    def __init__(self, first: NestedItem, second: NestedItem):
        self.first = first
        self.second = second
        super().__init__()


class CyclicSerializable(Serializable):
    """Serializable used to reject object cycles explicitly."""

    child: "CyclicSerializable | None"

    def __init__(self, child=None):
        self.child = child
        super().__init__()


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

    def test_serializable_dataclass_uses_the_tagged_object_contract(self):
        contract = JsonFile(SerializableWithSerializableDataclass)

        reconstructed = contract.loads(
            contract.dumps(
                SerializableWithSerializableDataclass(
                    SerializableDataclass(1),
                )
            )
        )

        assert isinstance(reconstructed.item, SerializableDataclass)
        assert reconstructed.item.value == 1

    def test_constructor_default_is_added_to_its_field_schema(self):
        schema = build_json_schema(SerializableWithDefault)

        assert schema["properties"]["label"] == {
            "type": "string",
            "default": "default",
        }


class TestSerializableInputValidation:
    """Test strict handling of serialized input boundaries."""

    def test_unexpected_field_is_rejected_without_kwargs(self):
        data = ClosedSerializable(1).to_dict()
        data["unexpected"] = 2

        with pytest.raises(ValueError, match="Unexpected serialized field"):
            ClosedSerializable.from_dict(data)

    def test_json_contract_rejects_extra_fields_without_kwargs(self):
        value = ClosedSerializable(1)
        setattr(value, "unexpected", 2)

        with pytest.raises(ValueError, match="Additional properties"):
            JsonFile(ClosedSerializable).dumps(value)

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

    @pytest.mark.parametrize(
        ("nested_value", "type_name"),
        [
            (NestedItem(2), "NestedItem"),
            (Seq("ACGT"), "Seq"),
            (ExternalLocation("reference-1", 0, 4), "ExternalLocation"),
        ],
    )
    def test_undeclared_metadata_rejects_values_that_lose_their_type(
        self,
        nested_value,
        type_name,
    ):
        original = SimpleSerializable(
            "test",
            1,
            metadata={"items": [{"value": nested_value}]},
        )

        with pytest.raises(TypeError, match=f"plain JSON data.*{type_name}"):
            original.to_dict()
        with pytest.raises(TypeError, match=f"plain JSON data.*{type_name}"):
            JsonFile(SimpleSerializable).dumps(original)

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


class TestSerializableGraph:
    """Test flat object-table serialization and reference reconstruction."""

    def test_shared_object_is_stored_once_and_restored_once(self):
        shared = NestedItem(1)
        document = _serialize_graph(SerializablePair(shared, shared))

        assert document == {
            "root": {
                "__class__": "SerializablePair",
                "__module__": "tests.unit.test_serializer",
                "first": {"$ref": "#/objects/NestedItem"},
                "second": {"$ref": "#/objects/NestedItem"},
            },
            "objects": {
                "NestedItem": {
                    "__class__": "NestedItem",
                    "__module__": "tests.unit.test_serializer",
                    "value": 1,
                },
            },
        }

        restored = _deserialize_graph(document, SerializablePair)

        assert restored.first is restored.second

    def test_root_list_can_be_reordered_without_breaking_references(self):
        shared = NestedItem(1)
        document = _serialize_graph(
            [
                SerializablePair(shared, shared),
                SerializablePair(shared, shared),
            ]
        )
        document["root"].reverse()

        restored = _deserialize_graph(document, list[SerializablePair])

        assert restored[0] is not restored[1]
        assert restored[0].first is restored[1].first

    def test_repeated_root_object_is_hoisted_but_its_unique_child_is_inline(self):
        pair = SerializablePair(NestedItem(1), NestedItem(2))
        document = _serialize_graph([pair, pair])

        assert document["root"] == [
            {"$ref": "#/objects/SerializablePair"},
            {"$ref": "#/objects/SerializablePair"},
        ]
        assert list(document["objects"]) == ["SerializablePair"]
        assert document["objects"]["SerializablePair"]["first"]["value"] == 1

        restored = JsonFile(list[SerializablePair]).loads(
            JsonFile(list[SerializablePair]).dumps([pair, pair])
        )

        assert restored[0] is restored[1]

    def test_multiple_shared_instances_of_one_class_get_local_suffixes(self):
        first = NestedItem(1)
        second = NestedItem(2)
        document = _serialize_graph([first, first, second, second])

        assert list(document["objects"]) == ["NestedItem-0", "NestedItem-1"]
        assert document["root"] == [
            {"$ref": "#/objects/NestedItem-0"},
            {"$ref": "#/objects/NestedItem-0"},
            {"$ref": "#/objects/NestedItem-1"},
            {"$ref": "#/objects/NestedItem-1"},
        ]

        restored = JsonFile(list[NestedItem]).loads(
            JsonFile(list[NestedItem]).dumps([first, first, second, second])
        )

        assert restored[0] is restored[1]
        assert restored[2] is restored[3]
        assert restored[0] is not restored[2]

    def test_equal_but_distinct_objects_are_not_merged(self):
        document = _serialize_graph(
            SerializablePair(NestedItem(1), NestedItem(1))
        )
        restored = _deserialize_graph(document, SerializablePair)

        assert document["objects"] == {}
        assert restored.first is not restored.second

    def test_declared_base_type_reconstructs_the_concrete_subtype(self):
        subtype = NestedItemSubtype(1)

        restored = _deserialize_graph(
            _serialize_graph(SerializablePair(subtype, subtype)),
            SerializablePair,
        )

        assert isinstance(restored.first, NestedItemSubtype)
        assert restored.first is restored.second

    def test_reference_and_class_shaped_metadata_remains_plain_data(self):
        metadata: dict[str, Any] = {
            "pointer": {"$ref": "#/objects/ordinary"},
            "source": {
                "__class__": "ordinary label",
                "__module__": "ordinary source",
            },
        }
        original = SimpleSerializable("test", 1, metadata=metadata)

        record_restored = SimpleSerializable.from_dict(original.to_dict())
        graph_restored = JsonFile(SimpleSerializable).loads(
            JsonFile(SimpleSerializable).dumps(original)
        )

        assert record_restored.metadata == metadata
        assert graph_restored.metadata == metadata

    def test_unknown_reference_is_rejected_by_validation(self):
        document = _serialize_graph(SerializablePair(NestedItem(1), NestedItem(2)))
        document["root"]["first"] = {
            "$ref": "#/objects/missing"
        }

        with pytest.raises(ValueError, match="Unknown Serializable graph reference"):
            _validate_graph(document, SerializablePair)

    def test_wrong_type_reference_is_rejected_by_validation(self):
        document = _serialize_graph(SerializablePair(NestedItem(1), NestedItem(2)))
        document["root"]["first"] = {"$ref": "#/objects/NestedItem"}
        document["objects"]["NestedItem"] = SerializablePair(
            NestedItem(1), NestedItem(2)
        ).to_dict()

        with pytest.raises(ValueError, match="Unknown NestedItem implementation"):
            _validate_graph(document, SerializablePair)

    def test_unreferenced_object_is_rejected_by_validation(self):
        item = NestedItem(1)
        document = _serialize_graph([item, item])
        document["objects"]["NestedItem-1"] = NestedItem(2).to_dict()

        with pytest.raises(ValueError, match="Unreferenced Serializable graph"):
            _validate_graph(document, list[NestedItem])

    def test_invalid_shared_record_is_rejected_by_file_contract(self):
        item = NestedItem(1)
        document = _serialize_graph([item, item])
        document["objects"]["NestedItem"]["value"] = "not-an-integer"

        with pytest.raises(ValueError, match=r"\$.objects.NestedItem.value"):
            JsonFile(list[NestedItem]).loads(json.dumps(document))

    def test_object_key_must_match_its_record_class(self):
        item = NestedItem(1)
        document = _serialize_graph([item, item])
        document["objects"]["Other-0"] = document["objects"].pop("NestedItem")
        document["root"] = {"$ref": "#/objects/Other-0"}

        with pytest.raises(ValueError, match="does not identify its NestedItem"):
            _validate_graph(document, NestedItem)

    def test_cyclic_reference_is_rejected_during_serialization(self):
        item = CyclicSerializable()
        item.child = item

        with pytest.raises(ValueError, match="Cyclic Serializable references"):
            _serialize_graph(item)

    def test_cyclic_reference_is_rejected_during_validation(self):
        document = {
            "root": {"$ref": "#/objects/CyclicSerializable"},
            "objects": {
                "CyclicSerializable": {
                    "__class__": "CyclicSerializable",
                    "__module__": "tests.unit.test_serializer",
                    "child": {"$ref": "#/objects/CyclicSerializable"},
                }
            },
        }

        with pytest.raises(ValueError, match="Cyclic Serializable graph"):
            JsonFile(CyclicSerializable).loads(json.dumps(document))

    def test_earlier_all_table_graph_is_still_readable(self):
        document = {
            "root": {"$ref": "#/objects/SerializablePair-0"},
            "objects": {
                "SerializablePair-0": {
                    "__class__": "SerializablePair",
                    "__module__": "tests.unit.test_serializer",
                    "first": {"$ref": "#/objects/NestedItem-0"},
                    "second": {"$ref": "#/objects/NestedItem-0"},
                },
                "NestedItem-0": {
                    "__class__": "NestedItem",
                    "__module__": "tests.unit.test_serializer",
                    "value": 1,
                },
            },
        }

        restored = JsonFile(SerializablePair).loads(json.dumps(document))

        assert restored.first is restored.second

    def test_existing_record_api_remains_unchanged(self):
        original = SerializablePair(NestedItem(1), NestedItem(2))

        restored = SerializablePair.from_dict(original.to_dict())

        assert restored.first.value == 1
        assert restored.second.value == 2
