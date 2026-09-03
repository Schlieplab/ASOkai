#!/usr/bin/env python
"""
Filename: tests/conftest.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Shared pytest fixtures for ASOkai tests.
License: LGPL-3.0-or-later
"""

from Bio.Seq import Seq
import pytest


@pytest.fixture
def sample_sequence():
    """Provide a sample Bio.Seq.Seq object."""
    return Seq("ATCGATCGATCGATCG")
