#!/usr/bin/env python
"""
Unit tests for TranscriptSite serialization/deserialization.
"""
import pytest
from Bio.Seq import Seq
from ASOkai.sites.transcript_site import TranscriptSite


@pytest.fixture
def sample_transcript_site(sample_sequence):
    """Create a sample TranscriptSite for testing."""
    return TranscriptSite(
        transcript_id="ENST00000001",
        t_start=10,
        t_end=26,
        sequence=sample_sequence,
        id="test_transcript_site"
    )


@pytest.mark.unit
@pytest.mark.serialization
class TestTranscriptSiteSerialization:
    """Test TranscriptSite serialization."""
    
    def test_transcript_id_serialized(self, sample_transcript_site):
        """Test that transcript_id is serialized."""
        data = sample_transcript_site.to_dict()
        
        assert 'transcript_id' in data
        assert data['transcript_id'] == "ENST00000001"
        
    def test_coordinates_serialized(self, sample_transcript_site):
        """Test that transcript coordinates are serialized."""
        data = sample_transcript_site.to_dict()
        
        assert 't_start' in data
        assert 't_end' in data
        assert data['t_start'] == 10
        assert data['t_end'] == 26
        
    def test_sequence_serialized(self, sample_transcript_site, sample_sequence):
        """Test that sequence is flattened in serialization."""
        data = sample_transcript_site.to_dict()
        
        assert 'sequence' in data
        assert data['sequence'] == str(sample_sequence)
        assert '_sequence' not in data
        
    def test_id_serialized(self, sample_transcript_site):
        """Test that id is serialized."""
        data = sample_transcript_site.to_dict()
        
        assert data['id'] == 'test_transcript_site'
        
    def test_metadata_present(self, sample_transcript_site):
        """Test that class metadata is present."""
        data = sample_transcript_site.to_dict()
        
        assert data['__class__'] == 'TranscriptSite'
        assert data['__module__'] == 'ASOkai.sites.transcript_site'
        
    def test_auto_generated_id_serialized(self, sample_sequence):
        """Test serialization with auto-generated ID."""
        site = TranscriptSite(
            transcript_id="ENST00000002",
            t_start=0,
            t_end=16,
            sequence=sample_sequence
        )
        
        data = site.to_dict()
        
        assert data['id'] == "ENST00000002:0-16"


@pytest.mark.unit
@pytest.mark.serialization
class TestTranscriptSiteDeserialization:
    """Test TranscriptSite deserialization."""
    
    def test_from_dict_basic(self, sample_sequence):
        """Test basic deserialization from dict."""
        data = {
            '__class__': 'TranscriptSite',
            '__module__': 'ASOkai.sites.transcript_site',
            'id': 'test_site',
            'transcript_id': 'ENST00000001',
            't_start': 10,
            't_end': 26,
            'sequence': str(sample_sequence)
        }
        
        obj = TranscriptSite.from_dict(data)
        
        assert isinstance(obj, TranscriptSite)
        assert obj.id == 'test_site'
        assert obj.transcript_id == 'ENST00000001'
        assert obj.t_start == 10
        assert obj.t_end == 26
        
    def test_sequence_reconstructed(self, sample_sequence):
        """Test that Seq object is reconstructed correctly."""
        data = {
            '__class__': 'TranscriptSite',
            '__module__': 'ASOkai.sites.transcript_site',
            'id': 'test_site',
            'transcript_id': 'ENST00000001',
            't_start': 10,
            't_end': 26,
            'sequence': str(sample_sequence)
        }
        
        obj = TranscriptSite.from_dict(data)
        
        assert isinstance(obj.sequence, Seq)
        assert str(obj.sequence) == str(sample_sequence)
        
    def test_coordinates_reconstructed(self, sample_sequence):
        """Test that coordinates are reconstructed correctly."""
        data = {
            '__class__': 'TranscriptSite',
            '__module__': 'ASOkai.sites.transcript_site',
            'id': 'test_site',
            'transcript_id': 'ENST00000001',
            't_start': 0,
            't_end': 16,
            'sequence': str(sample_sequence)
        }
        
        obj = TranscriptSite.from_dict(data)
        
        assert obj.t_start == 0
        assert obj.t_end == 16
        assert obj.t_end - obj.t_start == 16


@pytest.mark.unit
@pytest.mark.serialization
class TestTranscriptSiteRoundtrip:
    """Test complete serialization/deserialization roundtrip."""
    
    def test_roundtrip_preserves_data(self, sample_transcript_site):
        """Test that all data is preserved through roundtrip."""
        data = sample_transcript_site.to_dict()
        reconstructed = TranscriptSite.from_dict(data)
        
        assert reconstructed.id == sample_transcript_site.id
        assert reconstructed.transcript_id == sample_transcript_site.transcript_id
        assert reconstructed.t_start == sample_transcript_site.t_start
        assert reconstructed.t_end == sample_transcript_site.t_end
        assert str(reconstructed.sequence) == str(sample_transcript_site.sequence)


@pytest.mark.unit
class TestTranscriptSiteEquality:
    """Test TranscriptSite equality semantics."""

    def test_equality_true_for_same_fields(self, sample_sequence):
        a = TranscriptSite(
            transcript_id="ENST00000001",
            t_start=10,
            t_end=26,
            sequence=sample_sequence,
            id="test_site",
        )
        b = TranscriptSite(
            transcript_id="ENST00000001",
            t_start=10,
            t_end=26,
            sequence=sample_sequence,
            id="test_site",
        )

        assert a == b
        assert not (a != b)

    def test_equality_false_when_any_field_differs(self, sample_sequence):
        a = TranscriptSite(
            transcript_id="ENST00000001",
            t_start=10,
            t_end=26,
            sequence=sample_sequence,
            id="test_site",
        )
        b = TranscriptSite(
            transcript_id="ENST00000001",
            t_start=10,
            t_end=27,
            sequence=sample_sequence,
            id="test_site",
        )

        assert a != b

    def test_equality_with_other_type_is_false(self, sample_transcript_site):
        assert (sample_transcript_site == "not_a_site") is False
    
    def test_roundtrip_with_kwargs(self, sample_sequence):
        """Test that kwargs are preserved through roundtrip."""
        site = TranscriptSite(
            transcript_id="ENST00000001",
            t_start=10,
            t_end=26,
            sequence=sample_sequence,
            id="test_site",
            custom_attr="custom_value",
            score=0.85,
            annotation={"type": "exonic"}
        )
        
        data = site.to_dict()
        reconstructed = TranscriptSite.from_dict(data)
        
        assert reconstructed.custom_attr == "custom_value"
        assert reconstructed.score == 0.85
        assert reconstructed.annotation == {"type": "exonic"}
        
    def test_file_roundtrip(self, sample_transcript_site, temp_json_file):
        """Test roundtrip through file I/O."""
        sample_transcript_site.to_file(temp_json_file)
        reconstructed = TranscriptSite.from_file(temp_json_file)
        
        assert reconstructed.id == sample_transcript_site.id
        assert reconstructed.transcript_id == sample_transcript_site.transcript_id
        assert reconstructed.t_start == sample_transcript_site.t_start
        assert reconstructed.t_end == sample_transcript_site.t_end
        assert str(reconstructed.sequence) == str(sample_transcript_site.sequence)
        
    def test_multiple_sites_in_dict(self, sample_sequence):
        """Test serialization of multiple sites in a dictionary."""
        site1 = TranscriptSite(
            transcript_id="ENST00000001",
            t_start=10,
            t_end=26,
            sequence=sample_sequence,
            id="site1"
        )
        site2 = TranscriptSite(
            transcript_id="ENST00000001",
            t_start=50,
            t_end=66,
            sequence=sample_sequence,
            id="site2"
        )
        
        sites_dict = {"site1": site1, "site2": site2}
        
        from ASOkai.utils.serializer import Serializable
        serialized = Serializable()._serialize_value(sites_dict)
        deserialized = Serializable._deserialize_value(serialized)
        
        assert isinstance(deserialized['site1'], TranscriptSite)
        assert isinstance(deserialized['site2'], TranscriptSite)
        assert deserialized['site1'].id == 'site1'
        assert deserialized['site2'].id == 'site2'
        assert deserialized['site1'].transcript_id == 'ENST00000001'
        assert deserialized['site2'].transcript_id == 'ENST00000001'
        
    def test_roundtrip_with_different_transcripts(self, sample_sequence):
        """Test roundtrip with sites from different transcripts."""
        site1 = TranscriptSite(
            transcript_id="ENST00000001",
            t_start=0,
            t_end=16,
            sequence=sample_sequence
        )
        site2 = TranscriptSite(
            transcript_id="ENST00000002",
            t_start=0,
            t_end=16,
            sequence=sample_sequence
        )
        
        data1 = site1.to_dict()
        data2 = site2.to_dict()
        
        reconstructed1 = TranscriptSite.from_dict(data1)
        reconstructed2 = TranscriptSite.from_dict(data2)
        
        assert reconstructed1.transcript_id == "ENST00000001"
        assert reconstructed2.transcript_id == "ENST00000002"
        assert reconstructed1.id != reconstructed2.id
