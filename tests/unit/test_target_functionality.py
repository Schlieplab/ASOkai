#!/usr/bin/env python
"""
Functional tests for Target and TargetGene classes.
"""
import pytest
from Bio.Seq import Seq
from ASOkai.targets.target import Target
from ASOkai.targets.target_gene import TargetGene
from ASOkai.sites.genomic_site import GenomicSite


# Concrete implementation for testing Target abstract class
class ConcreteTarget(Target):
    """Concrete implementation of Target for testing."""
    pass


@pytest.fixture
def sample_sites_dict(sample_sequence):
    """Create a dict of sample sites for testing."""
    sites = {}
    for i in range(3):
        site = GenomicSite(
            chr="12",
            start=100 + i * 20,
            end=115 + i * 20,
            strand="+",
            sequence=sample_sequence,
            id=f"site_{i}"
        )
        sites[site.id] = site
    return sites


@pytest.mark.unit
class TestTargetBase:
    """Test Target base class functionality."""
    
    def test_target_initialization(self, sample_sites_dict):
        """Test Target initialization."""
        target = ConcreteTarget(
            id="target_001",
            sites=sample_sites_dict
        )
        
        assert target.id == "target_001"
        assert len(target.sites) == 3
    
    def test_sites_property(self, sample_sites_dict):
        """Test sites property returns a list of sites."""
        target = ConcreteTarget(
            id="target_001",
            sites=sample_sites_dict
        )
        
        assert isinstance(target.sites, list)
        assert {s.id for s in target.sites} == set(sample_sites_dict.keys())
    
    def test_sites_as_list(self, sample_sites_dict):
        """Test sites list contents."""
        target = ConcreteTarget(
            id="target_001",
            sites=sample_sites_dict
        )
        
        assert len(target.sites) == 3
        assert all(isinstance(s, GenomicSite) for s in target.sites)
    
    def test_site_by_id(self, sample_sites_dict):
        """Test retrieving site by ID."""
        target = ConcreteTarget(
            id="target_001",
            sites=sample_sites_dict
        )
        
        site = target.site_by_id("site_1")
        
        assert site.id == "site_1"
        assert isinstance(site, GenomicSite)
    
    def test_site_by_id_not_found(self, sample_sites_dict):
        """Test that ValueError is raised for non-existent site ID."""
        target = ConcreteTarget(
            id="target_001",
            sites=sample_sites_dict
        )
        
        with pytest.raises(ValueError, match="not found"):
            target.site_by_id("nonexistent_site")
    
    def test_empty_sites(self):
        """Test target with no sites."""
        target = ConcreteTarget(
            id="target_001",
            sites={}
        )
        
        assert len(target.sites) == 0
        assert target.sites == []
    
    def test_target_name_mapping(self):
        """Target uses attribute adapters for serialization (no name-map helper)."""
        target = ConcreteTarget(id="t", sites={})
        data = target.to_dict()
        assert "sites" in data


@pytest.mark.unit
class TestTargetGeneInitialization:
    """Test TargetGene initialization and properties."""
    
    def test_target_gene_basic_initialization(self, sample_sequence, sample_sites_dict):
        """Test basic TargetGene initialization."""
        gene = TargetGene(
            id="ENSG00000001",
            name="TEST_GENE",
            chr="12",
            start=100,
            end=1000,
            strand="+",
            sequence=sample_sequence,
            sites=sample_sites_dict
        )
        
        assert gene.id == "ENSG00000001"
        assert gene.name == "TEST_GENE"
        assert gene.chr == "12"
        assert gene.start == 100
        assert gene.end == 1000
        assert gene.strand == "+"
        assert gene.sequence == sample_sequence
        assert len(gene.sites) == 3
    
    def test_target_gene_sequence_property(self, sample_sequence, sample_sites_dict):
        """Test that sequence property works correctly."""
        gene = TargetGene(
            id="ENSG00000001",
            name="TEST_GENE",
            chr="12",
            start=100,
            end=1000,
            strand="+",
            sequence=sample_sequence,
            sites=sample_sites_dict
        )
        
        # sequence property should return _sequence
        assert gene.sequence == sample_sequence
        assert isinstance(gene.sequence, Seq)
    
    def test_target_gene_with_genome_reference(self, sample_sequence, sample_sites_dict):
        """Test TargetGene with genome parameter."""
        gene = TargetGene(
            id="ENSG00000001",
            name="TEST_GENE",
            chr="12",
            start=100,
            end=1000,
            strand="+",
            sequence=sample_sequence,
            sites=sample_sites_dict,
            genome=None
        )
        
        assert gene._genome is None
    
    def test_target_gene_name_mapping(self):
        """TargetGene uses registered attribute adapters for serialization."""
        gene = TargetGene(
            id="ENSG00000001",
            name="TEST_GENE",
            chr="12",
            start=100,
            end=1000,
            strand="+",
            sequence=Seq("ATCG"),
            sites={},
        )
        data = gene.to_dict()
        assert "sequence" in data
        assert "sites" in data


@pytest.mark.unit
class TestTargetGeneFunctionality:
    """Test TargetGene functional behavior."""
    
    def test_target_gene_site_access(self, sample_sequence, sample_sites_dict):
        """Test accessing sites from TargetGene."""
        gene = TargetGene(
            id="ENSG00000001",
            name="TEST_GENE",
            chr="12",
            start=100,
            end=1000,
            strand="+",
            sequence=sample_sequence,
            sites=sample_sites_dict
        )
        
        # Access site by ID
        site = gene.site_by_id("site_0")
        assert site.id == "site_0"
        
        # Access all sites as a list
        sites_list = gene.sites
        assert len(sites_list) == 3
        assert any(s.id == "site_0" for s in sites_list)
    
    def test_target_gene_with_many_sites(self, sample_sequence):
        """Test TargetGene with large number of sites."""
        sites = {}
        for i in range(100):
            site = GenomicSite(
                chr="12",
                start=100 + i * 20,
                end=115 + i * 20,
                strand="+",
                sequence=sample_sequence,
                id=f"site_{i}"
            )
            sites[site.id] = site
        
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
        
        assert len(gene.sites) == 100
    
    def test_target_gene_empty_sites(self, sample_sequence):
        """Test TargetGene with no sites."""
        gene = TargetGene(
            id="ENSG00000001",
            name="TEST_GENE",
            chr="12",
            start=100,
            end=1000,
            strand="+",
            sequence=sample_sequence,
            sites={}
        )
        
        assert len(gene.sites) == 0
        assert gene.sites == []
    
    def test_target_gene_different_strands(self, sample_sequence, sample_sites_dict):
        """Test genes on different strands."""
        gene_plus = TargetGene(
            id="ENSG00000001",
            name="GENE_PLUS",
            chr="12",
            start=100,
            end=1000,
            strand="+",
            sequence=sample_sequence,
            sites=sample_sites_dict
        )
        gene_minus = TargetGene(
            id="ENSG00000002",
            name="GENE_MINUS",
            chr="12",
            start=100,
            end=1000,
            strand="-",
            sequence=sample_sequence,
            sites=sample_sites_dict
        )
        
        assert gene_plus.strand == "+"
        assert gene_minus.strand == "-"


@pytest.mark.unit
class TestTargetGeneEdgeCases:
    """Test edge cases for TargetGene."""
    
    def test_gene_with_special_characters_in_name(self, sample_sequence):
        """Test gene with special characters in name."""
        gene = TargetGene(
            id="ENSG00000001",
            name="TEST-GENE_v2.1",
            chr="12",
            start=100,
            end=1000,
            strand="+",
            sequence=sample_sequence,
            sites={}
        )
        
        assert gene.name == "TEST-GENE_v2.1"
    
    def test_gene_with_dot_in_id(self, sample_sequence):
        """Test gene with version in ID (Ensembl style)."""
        gene = TargetGene(
            id="ENSG00000001.2",
            name="TEST_GENE",
            chr="12",
            start=100,
            end=1000,
            strand="+",
            sequence=sample_sequence,
            sites={}
        )
        
        assert gene.id == "ENSG00000001.2"
    
    def test_gene_on_mitochondrial_chromosome(self, sample_sequence):
        """Test gene on mitochondrial chromosome."""
        gene = TargetGene(
            id="ENSG00000198888",
            name="MT_GENE",
            chr="MT",
            start=1,
            end=100,
            strand="+",
            sequence=sample_sequence,
            sites={}
        )
        
        assert gene.chr == "MT"
    
    def test_very_large_gene(self, sample_sequence):
        """Test gene with very large genomic coordinates."""
        large_coord = 100000000
        gene = TargetGene(
            id="ENSG00000001",
            name="LARGE_GENE",
            chr="1",
            start=large_coord,
            end=large_coord + 1000000,
            strand="+",
            sequence=sample_sequence,
            sites={}
        )
        
        assert gene.start == large_coord
        locus_length = gene.end - gene.start + 1
        assert locus_length == 1000001
    
    def test_gene_with_kwargs(self, sample_sequence):
        """Test gene initialization with additional kwargs."""
        gene = TargetGene(
            id="ENSG00000001",
            name="TEST_GENE",
            chr="12",
            start=100,
            end=1000,
            strand="+",
            sequence=sample_sequence,
            sites={},
            custom_attribute="custom_value"
        )
        
        assert gene.custom_attribute == "custom_value"
