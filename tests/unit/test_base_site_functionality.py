#!/usr/bin/env python
"""
Functional tests for Site base class.
"""
import pytest
from Bio.Seq import Seq
from ASOkai.sites.site import Site


class ConcreteSite(Site):
    """Concrete implementation of Site for testing."""
    
    def __repr__(self):
        return f"ConcreteSite(id='{self.id}')"


@pytest.mark.unit
class TestSiteBase:
    """Test Site base class functionality."""
    
    def test_site_initialization(self, sample_sequence):
        """Test Site initialization."""
        site = ConcreteSite(id="test_site", sequence=sample_sequence)
        
        assert site.id == "test_site"
        assert site.sequence == sample_sequence
        assert isinstance(site._sequence, Seq)
    
    def test_site_sequence_property(self, sample_sequence):
        """Test that sequence property returns _sequence."""
        site = ConcreteSite(id="test_site", sequence=sample_sequence)
        
        assert site.sequence == site._sequence
    
    def test_site_with_kwargs(self, sample_sequence):
        """Test Site initialization with additional kwargs."""
        site = ConcreteSite(
            id="test_site",
            sequence=sample_sequence,
            custom_attr="custom_value"
        )
        
        assert site.custom_attr == "custom_value"

