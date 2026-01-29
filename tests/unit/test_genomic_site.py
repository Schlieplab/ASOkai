#!/usr/bin/env python
"""
Unit tests for GenomicSite serialization/deserialization.
"""
import pytest
from Bio.Seq import Seq
from GenomeUtils.Genome import Locus
from ASOkai.sites.genomic_site import GenomicSite


@pytest.fixture
def sample_genomic_site(sample_sequence):
    """Create a sample GenomicSite for testing."""
    return GenomicSite(
        chr="12",
        start=100,
        end=115,
        strand="+",
        sequence=sample_sequence,
        id="test_site"
    )


@pytest.mark.unit
@pytest.mark.serialization
class TestGenomicSiteSerialization:
    """Test GenomicSite serialization with flattened locus."""
    
    def test_locus_flattened_in_serialization(self, sample_genomic_site):
        """Test that locus is serialized as flattened components."""
        data = sample_genomic_site.to_dict()
        
        # Should have flattened locus components at top level
        assert 'chr' in data
        assert 'start' in data
        assert 'end' in data
        assert 'strand' in data
        
        # Should NOT have nested locus object
        assert 'locus' not in data
        
    def test_locus_components_correct(self, sample_genomic_site):
        """Test that locus components have correct values."""
        data = sample_genomic_site.to_dict()
        
        assert data['chr'] == "12"
        assert data['start'] == 100
        assert data['end'] == 115
        assert data['strand'] == "+"
        
    def test_sequence_serialized(self, sample_genomic_site, sample_sequence):
        """Test that sequence is flattened in serialization."""
        data = sample_genomic_site.to_dict()
        
        assert 'sequence' in data
        assert data['sequence'] == str(sample_sequence)
        assert '_sequence' not in data
        
    def test_id_serialized(self, sample_genomic_site):
        """Test that id is serialized."""
        data = sample_genomic_site.to_dict()
        
        assert data['id'] == 'test_site'
        
    def test_metadata_present(self, sample_genomic_site):
        """Test that class metadata is present."""
        data = sample_genomic_site.to_dict()
        
        assert data['__class__'] == 'GenomicSite'
        assert data['__module__'] == 'ASOkai.sites.genomic_site'
        
    def test_non_serializable_attrs_excluded(self, sample_genomic_site):
        """Test that _genome, _parent, _children are excluded."""
        # Manually set these attrs
        sample_genomic_site._genome = "should_not_serialize"
        sample_genomic_site._parent = "should_not_serialize"
        sample_genomic_site._children = []
        
        data = sample_genomic_site.to_dict()
        
        assert '_genome' not in data
        assert '_parent' not in data
        assert '_children' not in data


@pytest.mark.unit
@pytest.mark.serialization
class TestGenomicSiteDeserialization:
    """Test GenomicSite deserialization from flattened format."""
    
    def test_from_dict_with_flattened_locus(self, sample_sequence):
        """Test deserialization from flattened locus components."""
        data = {
            '__class__': 'GenomicSite',
            '__module__': 'ASOkai.sites.genomic_site',
            'id': 'test_site',
            'chr': '12',
            'start': 100,
            'end': 115,
            'strand': '+',
            'sequence': str(sample_sequence)
        }
        
        obj = GenomicSite.from_dict(data)
        
        assert isinstance(obj, GenomicSite)
        assert obj.id == 'test_site'
        assert obj.chr == '12'
        assert obj.start == 100
        assert obj.end == 115
        assert obj.strand == '+'
        
    def test_locus_reconstructed_correctly(self, sample_sequence):
        """Test that Locus object is reconstructed from components."""
        data = {
            '__class__': 'GenomicSite',
            '__module__': 'ASOkai.sites.genomic_site',
            'id': 'test_site',
            'chr': '12',
            'start': 100,
            'end': 115,
            'strand': '+',
            'sequence': str(sample_sequence)
        }
        
        obj = GenomicSite.from_dict(data)
        
        assert hasattr(obj, 'locus')
        assert isinstance(obj.locus, Locus)
        
    def test_sequence_reconstructed(self, sample_sequence):
        """Test that Seq object is reconstructed correctly."""
        data = {
            '__class__': 'GenomicSite',
            '__module__': 'ASOkai.sites.genomic_site',
            'id': 'test_site',
            'chr': '12',
            'start': 100,
            'end': 115,
            'strand': '+',
            'sequence': str(sample_sequence)
        }
        obj = GenomicSite.from_dict(data)
        assert isinstance(obj.sequence, Seq)
        assert str(obj.sequence) == str(sample_sequence)


@pytest.mark.unit
@pytest.mark.serialization
class TestGenomicSiteRoundtrip:
    """Test complete serialization/deserialization roundtrip."""
    
    def test_roundtrip_preserves_data(self, sample_genomic_site):
        """Test that all data is preserved through roundtrip."""
        data = sample_genomic_site.to_dict()
        reconstructed = GenomicSite.from_dict(data)
        
        assert reconstructed.id == sample_genomic_site.id
        assert reconstructed.locus.chr == sample_genomic_site.locus.chr
        assert reconstructed.locus.start == sample_genomic_site.locus.start
        assert reconstructed.locus.end == sample_genomic_site.locus.end
        assert reconstructed.locus.strand == sample_genomic_site.locus.strand
        assert str(reconstructed.sequence) == str(sample_genomic_site.sequence)
    
    def test_roundtrip_with_kwargs(self, sample_sequence):
        """Test that kwargs are preserved through roundtrip."""
        site = GenomicSite(
            chr="12",
            start=100,
            end=115,
            strand="+",
            sequence=sample_sequence,
            id="test_site",
            custom_attr="custom_value",
            score=0.95,
            metadata={"key": "value"}
        )
        
        data = site.to_dict()
        reconstructed = GenomicSite.from_dict(data)
        
        assert reconstructed.custom_attr == "custom_value"
        assert reconstructed.score == 0.95
        assert reconstructed.metadata == {"key": "value"}
        
    def test_file_roundtrip(self, sample_genomic_site, temp_json_file):
        """Test roundtrip through file I/O."""
        sample_genomic_site.to_file(temp_json_file)
        reconstructed = GenomicSite.from_file(temp_json_file)
        
        assert reconstructed.id == sample_genomic_site.id
        assert reconstructed.chr == sample_genomic_site.chr
        assert str(reconstructed.sequence) == str(sample_genomic_site.sequence)
        
    def test_multiple_sites_in_dict(self, sample_sequence):
        """Test serialization of multiple sites in a dictionary."""
        site1 = GenomicSite(
            chr="12", start=100, end=115, strand="+",
            sequence=sample_sequence, id="site1"
        )
        site2 = GenomicSite(
            chr="12", start=200, end=215, strand="-",
            sequence=sample_sequence, id="site2"
        )
        
        sites_dict = {"site1": site1, "site2": site2}
        
        # Simulate what happens in TargetGene
        from ASOkai.utils.serializer import Serializable
        serialized = Serializable()._serialize_value(sites_dict)
        deserialized = Serializable._deserialize_value(serialized)
        
        assert isinstance(deserialized['site1'], GenomicSite)
        assert isinstance(deserialized['site2'], GenomicSite)
        assert deserialized['site1'].id == 'site1'
        assert deserialized['site2'].id == 'site2'
