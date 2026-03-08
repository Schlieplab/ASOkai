#!/usr/bin/env python
"""
Functional tests for TargetGeneCreator class.
"""
import pytest
from ASOkai.targets.target_gene_creator import TargetGeneCreator


@pytest.mark.unit
class TestTargetGeneCreatorSiteIDPrefix:
    """Test TargetGeneCreator site ID prefix."""
    
    def test_target_gene_creator_inherits_prefix(self):
        """Test that TargetGeneCreator inherits SITE_ID_PREFIX_PARTS."""
        assert hasattr(TargetGeneCreator, 'SITE_ID_PREFIX_PARTS')
        assert TargetGeneCreator.SITE_ID_PREFIX_PARTS == ["ASOkai"]
    
    def test_target_gene_creator_site_id(self):
        """Test site ID generation from TargetGeneCreator."""
        generator = TargetGeneCreator.site_id_generator(
            extra_prefix_parts=["KRAS", "Premrna"]
        )
        
        first_id = next(generator)
        
        assert first_id == "ASOkai-KRAS-Premrna-S00001"
    
    def test_gene_name_in_prefix(self):
        """Test that gene name can be included in prefix."""
        gene_name = "TP53"
        region = "Exon"
        
        generator = TargetGeneCreator.site_id_generator(
            extra_prefix_parts=[gene_name, region]
        )
        
        site_id = next(generator)
        
        assert gene_name in site_id
        assert region in site_id
        assert site_id == "ASOkai-TP53-Exon-S00001"


@pytest.mark.unit
class TestTargetGeneCreatorMethods:
    """Test TargetGeneCreator specific methods."""
    
    def test_target_gene_creator_has_from_genome(self):
        """Test that TargetGeneCreator implements from_genome."""
        assert hasattr(TargetGeneCreator, 'from_genome')
        assert callable(TargetGeneCreator.from_genome)
    
    def test_target_gene_creator_has_from_file(self):
        """Test that TargetGeneCreator implements from_file."""
        assert hasattr(TargetGeneCreator, 'from_file')
        assert callable(TargetGeneCreator.from_file)
    
    def test_from_file_not_implemented(self):
        """Test that from_file is not yet implemented."""
        result = TargetGeneCreator.from_file("test.json")
        assert result is None
