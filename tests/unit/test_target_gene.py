#!/usr/bin/env python
"""
Unit tests for TargetGene serialization/deserialization.
"""
import pytest
from Bio.Seq import Seq
from GenomeUtils.Genome import Locus
from ASOkai.targets.target_gene import TargetGene
from ASOkai.sites.genomic_site import GenomicSite


@pytest.fixture
def sample_sites(sample_sequence):
    """Create sample sites for testing."""
    site1 = GenomicSite(
        chr="12", start=100, end=115, strand="+",
        sequence=sample_sequence, id="site1"
    )
    site2 = GenomicSite(
        chr="12", start=200, end=215, strand="-",
        sequence=sample_sequence, id="site2"
    )
    return {"site1": site1, "site2": site2}


@pytest.fixture
def sample_target_gene(sample_sequence, sample_sites):
    """Create a sample TargetGene for testing."""
    return TargetGene(
        id="ENSG00000001",
        name="TEST_GENE",
        chr="12",
        start=100,
        end=1000,
        strand="+",
        sequence=sample_sequence,
        sites=sample_sites
    )


@pytest.mark.unit
@pytest.mark.serialization
class TestTargetGeneSerialization:
    """Test TargetGene serialization with flattened locus."""
    
    def test_locus_flattened_in_serialization(self, sample_target_gene):
        """Test that locus is serialized as flattened components."""
        data = sample_target_gene.to_dict()
        
        # Should have flattened locus components at top level
        assert 'chr' in data
        assert 'start' in data
        assert 'end' in data
        assert 'strand' in data
        
        # Should NOT have nested locus object
        assert 'locus' not in data
        
    def test_locus_components_correct(self, sample_target_gene):
        """Test that locus components have correct values."""
        data = sample_target_gene.to_dict()
        
        assert data['chr'] == "12"
        assert data['start'] == 100
        assert data['end'] == 1000
        assert data['strand'] == "+"
        
    def test_gene_attributes_serialized(self, sample_target_gene):
        """Test that gene-specific attributes are serialized."""
        data = sample_target_gene.to_dict()
        
        assert data['id'] == 'ENSG00000001'
        assert data['name'] == 'TEST_GENE'
        
    def test_sequence_serialized(self, sample_target_gene, sample_sequence):
        """Test that sequence is flattened in serialization."""
        data = sample_target_gene.to_dict()
        
        assert 'sequence' in data
        assert data['sequence'] == str(sample_sequence)
        assert '_sequence' not in data
        
    def test_sites_serialized(self, sample_target_gene):
        """Test that target sites dictionary is serialized."""
        data = sample_target_gene.to_dict()
        
        assert 'sites' in data
        assert isinstance(data['sites'], dict)
        assert 'site1' in data['sites']
        assert 'site2' in data['sites']
        
    def test_sites_have_flattened_locus(self, sample_target_gene):
        """Test that nested sites also have flattened locus."""
        data = sample_target_gene.to_dict()
        
        site1_data = data['sites']['site1']
        
        # Each site should have flattened locus
        assert 'chr' in site1_data
        assert 'start' in site1_data
        assert 'end' in site1_data
        assert 'strand' in site1_data
        assert 'locus' not in site1_data
        
    def test_non_serializable_attrs_excluded(self, sample_target_gene):
        """Test that _genome, _parent, _children are excluded."""
        # Manually set these attrs
        sample_target_gene._genome = "should_not_serialize"
        sample_target_gene._parent = "should_not_serialize"
        sample_target_gene._children = []
        
        data = sample_target_gene.to_dict()
        
        assert '_genome' not in data
        assert '_parent' not in data
        assert '_children' not in data
        
    def test_metadata_present(self, sample_target_gene):
        """Test that class metadata is present."""
        data = sample_target_gene.to_dict()
        
        assert data['__class__'] == 'TargetGene'
        assert data['__module__'] == 'ASOkai.targets.target_gene'


@pytest.mark.unit
@pytest.mark.serialization
class TestTargetGeneDeserialization:
    """Test TargetGene deserialization from flattened format."""
    
    def test_from_dict_with_flattened_locus(self, sample_sequence):
        """Test deserialization from flattened locus components."""
        data = {
            '__class__': 'TargetGene',
            '__module__': 'ASOkai.targets.target_gene',
            'id': 'ENSG00000001',
            'name': 'TEST_GENE',
            'chr': '12',
            'start': 100,
            'end': 1000,
            'strand': '+',
            'sequence': str(sample_sequence),
            'sites': {}
        }
        
        obj = TargetGene.from_dict(data)
        
        assert isinstance(obj, TargetGene)
        assert obj.id == 'ENSG00000001'
        assert obj.name == 'TEST_GENE'
        assert obj.chr == '12'
        assert obj.start == 100
        assert obj.end == 1000
        assert obj.strand == '+'
        
    def test_locus_reconstructed_correctly(self, sample_sequence):
        """Test that Locus object is reconstructed from components."""
        data = {
            '__class__': 'TargetGene',
            '__module__': 'ASOkai.targets.target_gene',
            'id': 'ENSG00000001',
            'name': 'TEST_GENE',
            'chr': '12',
            'start': 100,
            'end': 1000,
            'strand': '+',
            'sequence': str(sample_sequence),
            'sites': {}
        }
        
        obj = TargetGene.from_dict(data)
        
        assert hasattr(obj, 'locus')
        assert isinstance(obj.locus, Locus)
        
    def test_sequence_reconstructed(self, sample_sequence):
        """Test that Seq object is reconstructed correctly."""
        data = {
            '__class__': 'TargetGene',
            '__module__': 'ASOkai.targets.target_gene',
            'id': 'ENSG00000001',
            'name': 'TEST_GENE',
            'chr': '12',
            'start': 100,
            'end': 1000,
            'strand': '+',
            'sequence': str(sample_sequence),
            'sites': {}
        }
        
        obj = TargetGene.from_dict(data)
        
        assert isinstance(obj.sequence, Seq)
        assert str(obj.sequence) == str(sample_sequence)
        
    def test_sites_reconstructed(self, sample_sequence):
        """Test that target sites are reconstructed as GenomicSite objects."""
        data = {
            '__class__': 'TargetGene',
            '__module__': 'ASOkai.targets.target_gene',
            'id': 'ENSG00000001',
            'name': 'TEST_GENE',
            'chr': '12',
            'start': 100,
            'end': 1000,
            'strand': '+',
            'sequence': str(sample_sequence),
            'sites': {
                'site1': {
                    '__class__': 'GenomicSite',
                    '__module__': 'ASOkai.sites.genomic_site',
                    'id': 'site1',
                    'chr': '12',
                    'start': 100,
                    'end': 115,
                    'strand': '+',
                    'sequence': str(sample_sequence)
                }
            }
        }
        
        obj = TargetGene.from_dict(data)
        
        assert any(site.id == 'site1' for site in obj.sites)
        site1 = obj.site_by_id('site1')
        assert isinstance(site1, GenomicSite)
        assert site1.id == 'site1'


@pytest.mark.unit
@pytest.mark.serialization
class TestTargetGeneRoundtrip:
    """Test complete serialization/deserialization roundtrip."""
    
    def test_roundtrip_preserves_gene_data(self, sample_target_gene):
        """Test that gene data is preserved through roundtrip."""
        data = sample_target_gene.to_dict()
        reconstructed = TargetGene.from_dict(data)
        
        assert reconstructed.id == sample_target_gene.id
        assert reconstructed.name == sample_target_gene.name
        assert reconstructed.chr == sample_target_gene.chr
        assert reconstructed.start == sample_target_gene.start
        assert reconstructed.end == sample_target_gene.end
        assert reconstructed.strand == sample_target_gene.strand
        assert str(reconstructed.sequence) == str(sample_target_gene.sequence)
        
    def test_roundtrip_preserves_sites(self, sample_target_gene):
        """Test that target sites are preserved through roundtrip."""
        data = sample_target_gene.to_dict()
        reconstructed = TargetGene.from_dict(data)
        
        assert len(reconstructed.sites) == len(sample_target_gene.sites)
        
        orig_by_id = {site.id: site for site in sample_target_gene.sites}
        recon_by_id = {site.id: site for site in reconstructed.sites}
        assert set(recon_by_id.keys()) == set(orig_by_id.keys())
        
        for site_id, orig_site in orig_by_id.items():
            recon_site = recon_by_id[site_id]
            
            assert recon_site.id == orig_site.id
            assert recon_site.chr == orig_site.chr
            assert recon_site.start == orig_site.start
            assert recon_site.end == orig_site.end
            assert recon_site.strand == orig_site.strand
            
    def test_file_roundtrip(self, sample_target_gene, temp_json_file):
        """Test roundtrip through file I/O."""
        sample_target_gene.to_file(temp_json_file)
        reconstructed = TargetGene.from_file(temp_json_file)
        
        assert reconstructed.id == sample_target_gene.id
        assert reconstructed.name == sample_target_gene.name
        assert len(reconstructed.sites) == len(sample_target_gene.sites)
        
    def test_large_number_of_sites(self, sample_sequence):
        """Test serialization with many target sites."""
        # Create gene with 100 sites
        sites = {}
        for i in range(100):
            site = GenomicSite(
                chr="12",
                start=100 + i * 20,
                end=115 + i * 20,
                strand="+" if i % 2 == 0 else "-",
                sequence=sample_sequence,
                id=f"site_{i}"
            )
            sites[f"site_{i}"] = site
            
        gene = TargetGene(
            id="ENSG00000001",
            name="TEST_GENE",
            chr="12",
            start=100,
            end=10000,
            strand="+",
            sequence=sample_sequence,
            sites=sites
        )
        
        # Roundtrip
        data = gene.to_dict()
        reconstructed = TargetGene.from_dict(data)
        
        assert len(reconstructed.sites) == 100
        recon_ids = {site.id for site in reconstructed.sites}
        assert all(f"site_{i}" in recon_ids for i in range(100))
    
    def test_roundtrip_with_kwargs(self, sample_sequence, locus_components):
        """Test that kwargs are preserved through roundtrip."""
        site = GenomicSite(
            chr=locus_components['chr'],
            start=locus_components['start'],
            end=locus_components['end'],
            strand=locus_components['strand'],
            sequence=sample_sequence,
            id="test_site"
        )
        
        gene = TargetGene(
            id="ENSG00000001",
            name="KRAS",
            chr="12",
            start=100,
            end=10000,
            strand="+",
            sequence=sample_sequence,
            sites={"test_site": site},
            custom_attr="custom_value",
            expression_level=123.45,
            annotations={"disease": "cancer", "pathway": "MAPK"}
        )
        
        data = gene.to_dict()
        reconstructed = TargetGene.from_dict(data)
        
        assert reconstructed.custom_attr == "custom_value"
        assert reconstructed.expression_level == 123.45
        assert reconstructed.annotations == {"disease": "cancer", "pathway": "MAPK"}
