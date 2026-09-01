#!/usr/bin/env python
"""
Filename: tests/unit/test_base_site_functionality.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Version: 0.1.1
Description: Functional tests for Site base class.
License: LGPL-3.0-or-later
"""

import inspect

import pytest

from ASOkai.Sites import Site


class ConcreteSite(Site):
    """Concrete implementation of Site for testing."""

    def __repr__(self) -> str:
        return f"ConcreteSite(id={self.id!r})"


@pytest.mark.unit
class TestSiteBase:
    """Test Site base class functionality."""

    def test_site_is_abstract(self):
        assert inspect.isabstract(Site)

    def test_site_exposes_sequence_and_metadata_attributes(
        self,
        sample_sequence,
    ):
        site = ConcreteSite(
            id="test_site",
            sequence=sample_sequence,
            metadata={"tags": ["reviewed"]},
        )

        assert site.id == "test_site"
        assert site.sequence is sample_sequence
        assert getattr(site, "metadata") == {"tags": ["reviewed"]}
