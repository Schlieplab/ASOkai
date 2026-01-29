#!/usr/bin/env python
"""
Integration tests for complete serialization workflows.
"""
import pytest
import json
from Bio.Seq import Seq
from ASOkai.targets.target_gene import TargetGene
from ASOkai.sites.genomic_site import GenomicSite


@pytest.fixture
def complex_target_gene():
    """Create a complex TargetGene with multiple sites and varied data."""
    gene_sequence = Seq("ATCGATCGATCGATCG" * 100)  # Long sequence
    
    # Create diverse target sites
    sites = {}
    for i in range(50):
        site_seq = Seq("ATCGATCGATCGATCG")
        site = GenomicSite(
            chr="12",
            start=1000 + i * 20,
            end=1015 + i * 20,
            strand="+" if i % 2 == 0 else "-",
            sequence=site_seq,
            id=f"ASOkai-TEST-S{i:06d}"
        )
        sites[site.id] = site
    
    return TargetGene(
        id="ENSG00000133703",
        name="KRAS",
        chr="12",
        start=25205246,
        end=25250936,
        strand="-",
        sequence=gene_sequence,
        target_sites=sites
    )


@pytest.mark.integration
@pytest.mark.serialization
class TestCompleteWorkflow:
    """Test complete serialization workflow scenarios."""
    
    def test_full_roundtrip_preserves_all_data(self, complex_target_gene):
        """Test that complex gene data survives full roundtrip."""
        # Serialize
        data = complex_target_gene.to_dict()
        
        # Deserialize
        reconstructed = TargetGene.from_dict(data)
        
        assert reconstructed.id == complex_target_gene.id
        assert reconstructed.name == complex_target_gene.name
        assert reconstructed.chr == complex_target_gene.chr
        assert reconstructed.start == complex_target_gene.start
        assert reconstructed.end == complex_target_gene.end
        assert reconstructed.strand == complex_target_gene.strand
        assert str(reconstructed.sequence) == str(complex_target_gene.sequence)
        
        # Verify all sites
        assert len(reconstructed.target_sites) == len(complex_target_gene.target_sites)
        orig_by_id = {site.id: site for site in complex_target_gene.target_sites}
        recon_by_id = {site.id: site for site in reconstructed.target_sites}
        assert set(recon_by_id.keys()) == set(orig_by_id.keys())
        for site_id, orig in orig_by_id.items():
            recon = recon_by_id[site_id]
            assert recon.id == orig.id
            assert recon.chr == orig.chr
            assert recon.start == orig.start
            assert recon.end == orig.end
            assert recon.strand == orig.strand
            assert str(recon.sequence) == str(orig.sequence)
    
    def test_file_roundtrip_with_complex_data(self, complex_target_gene, temp_json_file):
        """Test file I/O with complex nested data."""
        # Write to file
        complex_target_gene.to_file(temp_json_file)
        
        # Verify file is valid JSON
        with open(temp_json_file, 'r') as f:
            data = json.load(f)
        assert data['__class__'] == 'TargetGene'
        
        # Read back
        reconstructed = TargetGene.from_file(temp_json_file)
        
        # Verify
        assert reconstructed.id == complex_target_gene.id
        assert len(reconstructed.target_sites) == len(complex_target_gene.target_sites)
    
    def test_json_format_structure(self, complex_target_gene, temp_json_file):
        """Test that JSON has expected flattened structure."""
        complex_target_gene.to_file(temp_json_file)
        
        with open(temp_json_file, 'r') as f:
            data = json.load(f)
        
        # Gene should have flattened locus
        assert 'chr' in data
        assert 'start' in data
        assert 'end' in data
        assert 'strand' in data
        assert 'locus' not in data
        
        # Each site should also have flattened locus
        for site_id, site_data in data['target_sites'].items():
            assert 'chr' in site_data
            assert 'start' in site_data
            assert 'end' in site_data
            assert 'strand' in site_data
            assert 'locus' not in site_data
    
    def test_multiple_save_load_cycles(self, complex_target_gene, temp_dir):
        """Test that data survives multiple save/load cycles."""
        original = complex_target_gene
        
        for i in range(5):
            filepath = temp_dir / f"cycle_{i}.json"
            original.to_file(str(filepath))
            original = TargetGene.from_file(str(filepath))
        
        # After 5 cycles, data should still be intact
        assert original.id == complex_target_gene.id
        assert len(original.target_sites) == len(complex_target_gene.target_sites)
    
    def test_data_integrity_with_special_characters(self):
        """Test serialization with special characters in strings."""
        gene_sequence = Seq("ATCGATCG")
        site = GenomicSite(
            chr="chr12",
            start=100,
            end=115,
            strand="+",
            sequence=gene_sequence,
            id='site_with_"quotes"_and_\\backslash'
        )
        
        gene = TargetGene(
            id='ENSG_"special"',
            name='Gene\\with\\backslashes',
            chr="chr12",
            start=100,
            end=1000,
            strand="+",
            sequence=gene_sequence,
            target_sites={site.id: site}
        )
        
        # Roundtrip
        data = gene.to_dict()
        reconstructed = TargetGene.from_dict(data)
        
        assert reconstructed.id == gene.id
        assert reconstructed.name == gene.name
        assert site.id in {s.id for s in reconstructed.target_sites}


@pytest.mark.integration
@pytest.mark.serialization
class TestBackwardCompatibility:
    """Test handling of different data formats."""
    
    def test_missing_optional_attributes(self):
        """Test that missing optional attributes don't break deserialization."""
        data = {
            '__class__': 'TargetGene',
            '__module__': 'ASOkai.targets.target_gene',
            'id': 'ENSG00000001',
            'name': 'TEST',
            'chr': '12',
            'start': 100,
            'end': 1000,
            'strand': '+',
            'sequence': 'ATCGATCG',
            'target_sites': {}
            # Note: genome and chromosome are missing
        }
        
        obj = TargetGene.from_dict(data)
        assert obj.id == 'ENSG00000001'
    
    def test_empty_target_sites(self):
        """Test gene with no target sites."""
        gene_sequence = Seq("ATCGATCG")
        gene = TargetGene(
            id='ENSG00000001',
            name='TEST',
            chr="12",
            start=100,
            end=1000,
            strand="+",
            sequence=gene_sequence,
            target_sites={}
        )
        
        data = gene.to_dict()
        reconstructed = TargetGene.from_dict(data)
        
        assert len(reconstructed.target_sites) == 0


@pytest.mark.integration
@pytest.mark.serialization
class TestPerformance:
    """Test performance with large datasets."""
    
    def test_large_gene_serialization(self):
        """Test serialization of gene with many sites."""
        gene_sequence = Seq("ATCGATCG" * 10000)  # Very long sequence
        
        # Create 1000 sites
        sites = {}
        for i in range(1000):
            site = GenomicSite(
                chr="12",
                start=100 + i * 20,
                end=115 + i * 20,
                strand="+" if i % 2 == 0 else "-",
                sequence=Seq("ATCGATCGATCGATCG"),
                id=f"site_{i}"
            )
            sites[site.id] = site
        
        gene = TargetGene(
            id='ENSG00000001',
            name='TEST',
            chr="12",
            start=100,
            end=100000,
            strand="+",
            sequence=gene_sequence,
            target_sites=sites
        )
        
        # Should complete without error
        data = gene.to_dict()
        reconstructed = TargetGene.from_dict(data)
        
        assert len(reconstructed.target_sites) == 1000
    
    def test_file_size_reasonable(self, complex_target_gene, temp_json_file):
        """Test that file size is reasonable (JSON is human-readable)."""
        complex_target_gene.to_file(temp_json_file)
        
        import os
        file_size = os.path.getsize(temp_json_file)
        
        # With 50 sites, file should be < 1MB
        assert file_size < 1024 * 1024


@pytest.mark.integration
@pytest.mark.serialization  
class TestDataValidation:
    """Test that deserialized objects are valid."""
    
    def test_locus_object_is_valid(self):
        """Test that reconstructed Locus objects are functional."""
        data = {
            '__class__': 'GenomicSite',
            '__module__': 'ASOkai.sites.genomic_site',
            'id': 'test',
            'chr': '12',
            'start': 100,
            'end': 115,
            'strand': '+',
            'sequence': 'ATCGATCGATCGATCG'
        }
        
        site = GenomicSite.from_dict(data)
        
        assert str(site.locus) == "12:100-115,+"
        locus_length = site.end - site.start + 1
        assert locus_length == 16
    
    def test_sequence_object_is_valid(self):
        """Test that reconstructed Seq objects are functional."""
        data = {
            '__class__': 'GenomicSite',
            '__module__': 'ASOkai.sites.genomic_site',
            'id': 'test',
            'chr': '12',
            'start': 100,
            'end': 115,
            'strand': '+',
            'sequence': 'ATCGATCGATCGATCG'
        }
        
        site = GenomicSite.from_dict(data)
        
        # Sequence should be functional
        assert len(site.sequence) == 16
        assert site.sequence.complement() is not None
        assert site.sequence.reverse_complement() is not None
