#!/usr/bin/env python
"""
Functional tests for TargetCreator base class.
"""
import inspect

import pytest
from GenomeUtils.Genome import Genome

from ASOkai.Targets import Target, TargetCreator


@pytest.mark.unit
class TestTargetCreatorSiteIDGenerator:
    """Test site ID generator functionality."""
    
    def test_basic_site_id_generation(self):
        """Test basic site ID generation."""
        generator = TargetCreator.site_id_generator()
        
        first_id = next(generator)
        second_id = next(generator)
        third_id = next(generator)
        
        assert first_id == "ASOkai-S00001"
        assert second_id == "ASOkai-S00002"
        assert third_id == "ASOkai-S00003"
    
    def test_site_id_with_extra_prefix(self):
        """Test site ID generation with extra prefix parts."""
        generator = TargetCreator.site_id_generator(
            extra_prefix_parts=["KRAS", "Exon2"]
        )
        
        first_id = next(generator)
        
        assert first_id == "ASOkai-KRAS-Exon2-S00001"
    
    def test_site_id_with_custom_start(self):
        """Test site ID generation starting from custom number."""
        generator = TargetCreator.site_id_generator(start=100)
        
        first_id = next(generator)
        
        assert first_id == "ASOkai-S00100"
    
    def test_site_id_multiple_extra_parts(self):
        """Test site ID with multiple extra prefix parts."""
        generator = TargetCreator.site_id_generator(
            extra_prefix_parts=["GENE1", "Transcript1", "Region1"]
        )
        
        first_id = next(generator)
        
        assert first_id == "ASOkai-GENE1-Transcript1-Region1-S00001"
    
    def test_site_id_incrementation(self):
        """Test that site IDs increment correctly."""
        generator = TargetCreator.site_id_generator(start=1)
        
        ids = [next(generator) for _ in range(10)]
        
        assert len(ids) == 10
        assert ids[0] == "ASOkai-S00001"
        assert ids[9] == "ASOkai-S00010"
    
    def test_site_id_zero_padding(self):
        """Test that site IDs have correct zero padding."""
        generator = TargetCreator.site_id_generator(start=99)
        
        id_99 = next(generator)
        id_100 = next(generator)
        id_1000 = next(generator)
        
        assert id_99 == "ASOkai-S00099"
        assert id_100 == "ASOkai-S00100"
        for _ in range(898):
            next(generator)
        id_1000 = next(generator)
        assert id_1000 == "ASOkai-S01000"
    
    def test_site_id_generator_is_iterator(self):
        """Test that site_id_generator returns an iterator."""
        generator = TargetCreator.site_id_generator()
        
        assert hasattr(generator, '__iter__')
        assert hasattr(generator, '__next__')
    
    def test_multiple_independent_generators(self):
        """Test that multiple generators work independently."""
        gen1 = TargetCreator.site_id_generator()
        gen2 = TargetCreator.site_id_generator(start=100)
        
        assert next(gen1) == "ASOkai-S00001"
        assert next(gen2) == "ASOkai-S00100"
        assert next(gen1) == "ASOkai-S00002"
        assert next(gen2) == "ASOkai-S00101"


@pytest.mark.unit
class TestTargetCreatorAbstractMethods:
    """Test that TargetCreator abstract methods are defined."""
    
    def test_from_file_is_classmethod(self):
        """Test that from_file is a classmethod."""
        assert hasattr(TargetCreator, 'from_file')
        assert isinstance(TargetCreator.__dict__['from_file'], classmethod)
    
    def test_from_genome_is_classmethod(self):
        """Test that from_genome is a classmethod."""
        assert hasattr(TargetCreator, 'from_genome')
        assert isinstance(TargetCreator.__dict__['from_genome'], classmethod)
    
    def test_cannot_instantiate_target_creator(self):
        """Test that TargetCreator cannot be instantiated."""
        assert inspect.isabstract(TargetCreator)


@pytest.mark.unit
class TestSiteIDFormatting:
    """Test site ID formatting edge cases."""
    
    def test_site_id_with_spaces_in_extra_parts(self):
        """Test handling of spaces in extra prefix parts."""
        generator = TargetCreator.site_id_generator(
            extra_prefix_parts=["Gene Name", "Region Name"]
        )
        
        first_id = next(generator)
        
        assert first_id == "ASOkai-Gene Name-Region Name-S00001"
    
    def test_site_id_with_empty_extra_parts(self):
        """Test site ID generation with empty extra parts list."""
        generator = TargetCreator.site_id_generator(
            extra_prefix_parts=[]
        )
        
        first_id = next(generator)
        
        assert first_id == "ASOkai-S00001"
    
    def test_site_id_with_none_extra_parts(self):
        """Test site ID generation with None extra parts."""
        generator = TargetCreator.site_id_generator(
            extra_prefix_parts=None
        )
        
        first_id = next(generator)
        
        assert first_id == "ASOkai-S00001"
    
    def test_site_id_large_numbers(self):
        """Test site ID with very large numbers."""
        generator = TargetCreator.site_id_generator(start=999999)
        
        first_id = next(generator)
        second_id = next(generator)
        
        assert first_id == "ASOkai-S999999"
        assert second_id == "ASOkai-S1000000"
    
    def test_site_id_format_consistency(self):
        """Test that all generated IDs follow consistent format."""
        generator = TargetCreator.site_id_generator(
            extra_prefix_parts=["TEST"]
        )
        
        ids = [next(generator) for _ in range(100)]
        
        assert all(id.startswith("ASOkai-TEST-S") for id in ids)
        
        numbers = [int(id.split('-S')[-1]) for id in ids]
        assert numbers == list(range(1, 101))


@pytest.mark.unit
class TestTargetCreatorClassAttributes:
    """Test TargetCreator class attributes."""
    
    def test_site_id_prefix_parts_is_list(self):
        """Test that SITE_ID_PREFIX_PARTS is a list."""
        assert isinstance(TargetCreator.SITE_ID_PREFIX_PARTS, list)
    
    def test_site_id_prefix_parts_not_empty(self):
        """Test that SITE_ID_PREFIX_PARTS is not empty."""
        assert len(TargetCreator.SITE_ID_PREFIX_PARTS) > 0
    
    def test_site_id_prefix_default_value(self):
        """Test default value of SITE_ID_PREFIX_PARTS."""
        assert TargetCreator.SITE_ID_PREFIX_PARTS == ["ASOkai"]
    
    def test_site_id_prefix_can_be_extended(self):
        """Test that SITE_ID_PREFIX_PARTS can be extended in subclass."""
        class CustomTargetCreator(TargetCreator):
            SITE_ID_PREFIX_PARTS = ["ASOkai", "Custom"]
            
            @classmethod
            def from_file(cls, file_path: str) -> Target:
                raise NotImplementedError
            
            @classmethod
            def from_genome(
                cls,
                genome: Genome,
                target_id: str | None = None,
                target_name: str | None = None,
                *,
                k: int,
                region: str = "exonic_only",
            ) -> Target:
                raise NotImplementedError
        
        generator = CustomTargetCreator.site_id_generator()
        first_id = next(generator)
        
        assert first_id == "ASOkai-Custom-S00001"
