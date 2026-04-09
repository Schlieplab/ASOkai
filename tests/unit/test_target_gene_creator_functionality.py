#!/usr/bin/env python
"""
Functional tests for TargetGeneCreator class.
"""
import pytest
from unittest.mock import MagicMock
from Bio.Seq import Seq

from ASOkai.Targets import TargetGeneCreator


@pytest.fixture
def mock_genome_and_gene(sample_sequence):
    """Mock genome and gene for from_genome tests."""
    gene = MagicMock()
    gene.id = "ENSG00000133703"
    gene.name = "KRAS"
    gene.chr = "12"
    gene.start = 100
    gene.end = 500
    gene.strand = "+"
    gene.sequence = sample_sequence
    gene.transcripts = []
    gene.get_chromosome.return_value = None

    genome = MagicMock()
    genome.gene_by_id.return_value = gene
    genome.gene_by_name.return_value = gene
    genome.get_sequence_by_locus.return_value = sample_sequence

    return genome, gene


@pytest.mark.unit
class TestTargetGeneCreatorFromGenome:
    """Test from_genome with target_id and target_name."""

    def test_from_genome_raises_when_neither_target_id_nor_target_name(self, mock_genome_and_gene):
        """Test that ValueError is raised when neither target_id nor target_name provided."""
        genome, _ = mock_genome_and_gene

        with pytest.raises(ValueError, match="exactly one of target_id or target_name"):
            TargetGeneCreator.from_genome(genome, target_id=None, target_name=None, k=16)

    def test_from_genome_raises_when_both_target_id_and_target_name(self, mock_genome_and_gene):
        """Test that ValueError is raised when both target_id and target_name provided."""
        genome, _ = mock_genome_and_gene

        with pytest.raises(ValueError, match="exactly one of target_id or target_name"):
            TargetGeneCreator.from_genome(
                genome, target_id="ENSG00000133703", target_name="KRAS", k=16
            )

    def test_from_genome_by_target_id_calls_gene_by_id(self, mock_genome_and_gene):
        """Test that from_genome with target_id uses genome.gene_by_id."""
        genome, gene = mock_genome_and_gene

        result = TargetGeneCreator.from_genome(genome, target_id="ENSG00000133703", k=16)

        genome.gene_by_id.assert_called_once_with("ENSG00000133703")
        genome.gene_by_name.assert_not_called()
        assert result.id == gene.id
        assert result.name == gene.name

    def test_from_genome_by_target_name_calls_gene_by_name(self, mock_genome_and_gene):
        """Test that from_genome with target_name uses genome.gene_by_name."""
        genome, gene = mock_genome_and_gene

        result = TargetGeneCreator.from_genome(genome, target_name="KRAS", k=16)

        genome.gene_by_name.assert_called_once_with("KRAS")
        genome.gene_by_id.assert_not_called()
        assert result.id == gene.id
        assert result.name == gene.name


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
