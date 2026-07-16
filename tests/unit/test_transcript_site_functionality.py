#!/usr/bin/env python
"""
Functional tests for TranscriptSite class.
"""
from typing import Any, cast

import pytest
from Bio.Seq import Seq
from ASOkai.Sites import TranscriptSite


@pytest.mark.unit
class TestTranscriptSiteInitialization:
    """Test TranscriptSite initialization."""
    
    def test_basic_initialization(self, sample_sequence):
        """Test basic TranscriptSite initialization."""
        site = TranscriptSite(
            transcript_id="ENST00000001",
            t_start=10,
            t_end=25,
            sequence=sample_sequence,
            id="test_site"
        )
        
        assert site.transcript_id == "ENST00000001"
        assert site.t_start == 10
        assert site.t_end == 25
        assert site.id == "test_site"
        assert site.sequence == sample_sequence
    
    def test_auto_id_generation(self, sample_sequence):
        """Test automatic ID generation from transcript coordinates."""
        site = TranscriptSite(
            transcript_id="ENST00000001",
            t_start=10,
            t_end=25,
            sequence=sample_sequence
        )
        
        assert site.id == "ENST00000001:10-25"
    
    def test_initialization_with_kwargs(self, sample_sequence):
        """Test initialization with additional kwargs."""
        site = TranscriptSite(
            transcript_id="ENST00000001",
            t_start=10,
            t_end=25,
            sequence=sample_sequence,
            custom_attr="custom_value"
        )
        
        assert getattr(site, "custom_attr") == "custom_value"


@pytest.mark.unit
class TestTranscriptSiteProperties:
    """Test TranscriptSite properties and methods."""
    
    def test_transcript_coordinates(self, sample_sequence):
        """Test that transcript coordinates are stored correctly."""
        site = TranscriptSite(
            transcript_id="ENST00000001",
            t_start=0,
            t_end=16,
            sequence=sample_sequence
        )
        
        assert site.t_start == 0
        assert site.t_end == 16
        assert site.t_end - site.t_start == 16
    
    def test_site_length(self, sample_sequence):
        """Test that site length matches coordinates."""
        site = TranscriptSite(
            transcript_id="ENST00000001",
            t_start=10,
            t_end=26,
            sequence=sample_sequence
        )
        
        assert site.t_end - site.t_start == 16
        assert len(site.sequence) == 16
    
    def test_different_transcript_ids(self, sample_sequence):
        """Test sites with different transcript IDs."""
        site1 = TranscriptSite(
            transcript_id="ENST00000001",
            t_start=10,
            t_end=25,
            sequence=sample_sequence
        )
        site2 = TranscriptSite(
            transcript_id="ENST00000002",
            t_start=10,
            t_end=25,
            sequence=sample_sequence
        )
        
        assert site1.transcript_id != site2.transcript_id
        assert site1.id != site2.id


@pytest.mark.unit
class TestTranscriptSiteCoordinates:
    """Test various coordinate scenarios for TranscriptSite."""
    
    def test_site_at_transcript_start(self, sample_sequence):
        """Test site at the beginning of transcript."""
        site = TranscriptSite(
            transcript_id="ENST00000001",
            t_start=0,
            t_end=16,
            sequence=sample_sequence
        )
        
        assert site.t_start == 0
    
    def test_site_with_large_coordinates(self):
        """Test site with large transcript coordinates."""
        long_sequence = Seq("A" * 50)
        site = TranscriptSite(
            transcript_id="ENST00000001",
            t_start=1000,
            t_end=1050,
            sequence=long_sequence
        )
        
        assert site.t_start == 1000
        assert site.t_end == 1050
    
    def test_overlapping_sites_same_transcript(self, sample_sequence):
        """Test multiple overlapping sites on same transcript."""
        site1 = TranscriptSite(
            transcript_id="ENST00000001",
            t_start=10,
            t_end=26,
            sequence=sample_sequence,
            id="site1"
        )
        site2 = TranscriptSite(
            transcript_id="ENST00000001",
            t_start=20,
            t_end=36,
            sequence=sample_sequence,
            id="site2"
        )
        
        assert site1.transcript_id == site2.transcript_id
        assert site1.t_start < site2.t_start
        assert site1.t_end > site2.t_start
    
    def test_adjacent_sites(self, sample_sequence):
        """Test adjacent non-overlapping sites."""
        site1 = TranscriptSite(
            transcript_id="ENST00000001",
            t_start=0,
            t_end=16,
            sequence=sample_sequence,
            id="site1"
        )
        site2 = TranscriptSite(
            transcript_id="ENST00000001",
            t_start=16,
            t_end=32,
            sequence=sample_sequence,
            id="site2"
        )
        
        assert site1.t_end == site2.t_start


@pytest.mark.unit
class TestTranscriptSiteSequence:
    """Test sequence handling in TranscriptSite."""
    
    def test_sequence_storage(self, sample_sequence):
        """Test that sequence is stored correctly."""
        site = TranscriptSite(
            transcript_id="ENST00000001",
            t_start=0,
            t_end=16,
            sequence=sample_sequence
        )
        
        assert site.sequence == sample_sequence
        assert isinstance(site.sequence, Seq)
    
    def test_sequence_operations(self, sample_sequence):
        """Test that Bio.Seq operations work on site sequence."""
        site = TranscriptSite(
            transcript_id="ENST00000001",
            t_start=0,
            t_end=16,
            sequence=sample_sequence
        )
        
        assert site.sequence.complement() is not None
        assert site.sequence.reverse_complement() is not None
        assert len(site.sequence) == len(sample_sequence)
    
    def test_different_sequences(self):
        """Test sites with different sequences."""
        seq1 = Seq("AAAA" * 4)
        seq2 = Seq("GGGG" * 4)
        
        site1 = TranscriptSite(
            transcript_id="ENST00000001",
            t_start=0,
            t_end=16,
            sequence=seq1
        )
        site2 = TranscriptSite(
            transcript_id="ENST00000001",
            t_start=20,
            t_end=36,
            sequence=seq2
        )
        
        assert str(site1.sequence) != str(site2.sequence)


@pytest.mark.unit
class TestTranscriptSiteToGenomic:
    """Test to_genomic method."""
    
    def test_to_genomic_method_exists(self, sample_sequence):
        """Test that to_genomic method exists."""
        site = TranscriptSite(
            transcript_id="ENST00000001",
            t_start=0,
            t_end=16,
            sequence=sample_sequence
        )
        
        assert hasattr(site, 'to_genomic')
        assert callable(site.to_genomic)
    
    def test_to_genomic_not_implemented(self, sample_sequence):
        """Test that to_genomic is not yet implemented."""
        site = TranscriptSite(
            transcript_id="ENST00000001",
            t_start=0,
            t_end=16,
            sequence=sample_sequence
        )
        
        with pytest.raises(NotImplementedError):
            site.to_genomic(cast(Any, None))


@pytest.mark.unit
class TestTranscriptSiteEdgeCases:
    """Test edge cases for TranscriptSite."""
    
    def test_single_base_site(self):
        """Test site with single base."""
        single_base = Seq("A")
        site = TranscriptSite(
            transcript_id="ENST00000001",
            t_start=10,
            t_end=11,
            sequence=single_base
        )
        
        assert site.t_end - site.t_start == 1
        assert len(site.sequence) == 1
    
    def test_very_long_site(self):
        """Test site with very long sequence."""
        long_seq = Seq("ATCG" * 250)
        site = TranscriptSite(
            transcript_id="ENST00000001",
            t_start=0,
            t_end=1000,
            sequence=long_seq
        )
        
        assert len(site.sequence) == 1000
        assert site.t_end - site.t_start == 1000
    
    def test_site_id_with_special_characters(self):
        """Test transcript IDs with special characters."""
        site = TranscriptSite(
            transcript_id="ENST00000001.2",
            t_start=0,
            t_end=16,
            sequence=Seq("ATCGATCGATCGATCG")
        )
        
        assert "ENST00000001.2" in site.id
        assert site.transcript_id == "ENST00000001.2"
