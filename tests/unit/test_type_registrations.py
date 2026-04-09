#!/usr/bin/env python
"""
Unit tests for attribute adapters registered on Serializable.
"""
import pytest
from ASOkai.Utils import Serializable


@pytest.mark.unit
@pytest.mark.serialization
class TestAttributeAdapters:
    """Test external-type handling via registered attribute adapters."""
    
    def test_sequence_adapter_registered(self):
        """Seq is handled via the registered _sequence <-> sequence adapter."""
        assert '_sequence' in Serializable._attribute_serializers
        serialized_name, _serialize_func, flatten = Serializable._attribute_serializers['_sequence']
        assert serialized_name == 'sequence'
        assert flatten is False
        
        # Deserialization is keyed by incoming/init-arg name ("sequence")
        assert 'sequence' in Serializable._attribute_deserializers
        
    def test_locus_adapter_registered_and_flattened(self, sample_locus):
        """Locus is flattened into chr/start/end/strand when present as an attribute."""
        assert 'locus' in Serializable._attribute_serializers
        _serialized_name, serialize_func, flatten = Serializable._attribute_serializers['locus']
        assert flatten is True
        components = serialize_func(sample_locus)
        assert components == {
            'chr': sample_locus.chr,
            'start': sample_locus.start,
            'end': sample_locus.end,
            'strand': sample_locus.strand,
        }
