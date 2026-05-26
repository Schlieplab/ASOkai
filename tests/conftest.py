#!/usr/bin/env python
"""
Shared pytest fixtures for ASOkai tests.
"""
import pytest
import tempfile
import os
from pathlib import Path
from Bio.Seq import Seq
from GenomeUtils.Genome import Locus


@pytest.fixture
def sample_sequence():
    """Provide a sample Bio.Seq.Seq object."""
    return Seq("ATCGATCGATCGATCG")


@pytest.fixture
def sample_locus():
    """Provide a sample GenomeUtils.Locus object."""
    return Locus(chr="12", start=100, end=200, strand="+")


@pytest.fixture
def locus_components():
    """Provide locus components as a dict."""
    return {
        "chr": "12",
        "start": 100,
        "end": 200,
        "strand": "+"
    }


@pytest.fixture
def temp_json_file():
    """Provide a temporary JSON file path."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        temp_path = f.name
    yield temp_path
    # Cleanup
    if os.path.exists(temp_path):
        os.remove(temp_path)


@pytest.fixture
def temp_dir():
    """Provide a temporary directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)
