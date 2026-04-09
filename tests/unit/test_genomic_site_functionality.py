#!/usr/bin/env python
"""
Functional tests for GenomicSite class.
"""
import pytest
from Bio.Seq import Seq
from GenomeUtils.Genome import Locus
from ASOkai.Sites import GenomicSite


@pytest.mark.unit
class TestGenomicSiteFunctionality:
    """Test GenomicSite functional behavior."""
    
    def test_genomic_site_initialization(self, sample_sequence):
        """Test GenomicSite initialization."""
        site = GenomicSite(
            chr="12",
            start=100,
            end=115,
            strand="+",
            sequence=sample_sequence,
            id="test_site"
        )
        
        assert site.id == "test_site"
        assert site.sequence == sample_sequence
        assert site.chr == "12"
        assert site.start == 100
        assert site.end == 115
        assert site.strand == "+"
        assert site.locus.chr == "12"
        assert site.locus.start == 100
        assert site.locus.end == 115
        assert site.locus.strand == "+"
    
    def test_genomic_site_auto_id_generation(self, sample_sequence):
        """Test automatic ID generation from locus."""
        site = GenomicSite(
            chr="12",
            start=100,
            end=115,
            strand="+",
            sequence=sample_sequence
        )
        
        assert site.id == str(site.locus)
    
    def test_genomic_site_locus_property(self, sample_sequence):
        """Test that locus property returns Locus object."""
        site = GenomicSite(
            chr="12",
            start=100,
            end=115,
            strand="+",
            sequence=sample_sequence
        )
        
        assert isinstance(site.locus, Locus)
        assert site.chr == "12"
        assert site.locus.chr == "12"
    
    def test_genomic_site_repr(self, sample_sequence):
        """Test string representation."""
        site = GenomicSite(
            chr="12",
            start=100,
            end=115,
            strand="+",
            sequence=sample_sequence,
            id="test_site"
        )
        
        repr_str = repr(site)
        
        assert "GenomicSite" in repr_str
        assert "test_site" in repr_str
    
    def test_genomic_site_different_strands(self, sample_sequence):
        """Test sites on different strands."""
        site_plus = GenomicSite(
            chr="12", start=100, end=115, strand="+",
            sequence=sample_sequence, id="plus"
        )
        site_minus = GenomicSite(
            chr="12", start=100, end=115, strand="-",
            sequence=sample_sequence, id="minus"
        )
        
        assert site_plus.strand == "+"
        assert site_minus.strand == "-"
        assert site_plus.locus.strand == "+"
        assert site_minus.locus.strand == "-"
    
    def test_genomic_site_with_genome_reference(self, sample_sequence):
        """Test GenomicSite with genome parameter."""
        site = GenomicSite(
            chr="12",
            start=100,
            end=115,
            strand="+",
            sequence=sample_sequence,
            genome=None
        )
        
        assert site._genome is None
    
    def test_genomic_site_length(self, sample_sequence):
        """Test that site length matches locus length."""
        site = GenomicSite(
            chr="12",
            start=100,
            end=115,
            strand="+",
            sequence=sample_sequence
        )
        
        locus_length = site.end - site.start + 1
        assert locus_length == 16
        assert len(site.sequence) == 16
        assert (site.locus.end - site.locus.start + 1) == 16


@pytest.mark.unit
class TestGenomicSiteComparison:
    """Test GenomicSite comparison and uniqueness."""
    
    def test_sites_with_same_locus(self, sample_sequence):
        """Test creating multiple sites at same locus."""
        site1 = GenomicSite(
            chr="12", start=100, end=115, strand="+",
            sequence=sample_sequence, id="site1"
        )
        site2 = GenomicSite(
            chr="12", start=100, end=115, strand="+",
            sequence=sample_sequence, id="site2"
        )
        
        assert site1.id != site2.id
        assert site1.chr == site2.chr
        assert site1.start == site2.start
        assert site1.end == site2.end
    
    def test_sites_with_different_positions(self, sample_sequence):
        """Test sites at different genomic positions."""
        site1 = GenomicSite(
            chr="12", start=100, end=115, strand="+",
            sequence=sample_sequence, id="site1"
        )
        site2 = GenomicSite(
            chr="12", start=200, end=215, strand="+",
            sequence=sample_sequence, id="site2"
        )
        
        assert site1.start != site2.start
        assert site1.end != site2.end
        assert site1 != site2
    
    def test_sites_on_different_chromosomes(self, sample_sequence):
        """Test sites on different chromosomes."""
        site1 = GenomicSite(
            chr="12", start=100, end=115, strand="+",
            sequence=sample_sequence, id="site1"
        )
        site2 = GenomicSite(
            chr="X", start=100, end=115, strand="+",
            sequence=sample_sequence, id="site2"
        )
        
        assert site1.chr != site2.chr
        assert site1 != site2


@pytest.mark.unit
class TestGenomicSiteEdgeCases:
    """Test edge cases for GenomicSite."""
    
    def test_site_with_start_one(self, sample_sequence):
        """Test site with start position of 1 (minimum valid)."""
        site = GenomicSite(
            chr="12", start=1, end=16, strand="+",
            sequence=sample_sequence
        )
        
        assert site.start == 1
        assert site.locus.start == 1
    
    def test_site_with_very_large_coordinates(self, sample_sequence):
        """Test site with large genomic coordinates."""
        large_coord = 100000000
        site = GenomicSite(
            chr="12",
            start=large_coord,
            end=large_coord + 15,
            strand="+",
            sequence=sample_sequence
        )
        
        assert site.start == large_coord
        assert site.end == large_coord + 15
    
    def test_site_with_special_chromosome_names(self, sample_sequence):
        """Test sites with various chromosome naming conventions."""
        for chr_name in ["chr12", "12", "X", "chrX", "MT", "chrM"]:
            site = GenomicSite(
                chr=chr_name,
                start=100,
                end=115,
                strand="+",
                sequence=sample_sequence
            )
            
            assert site.chr == chr_name
            assert site.locus.chr == chr_name
