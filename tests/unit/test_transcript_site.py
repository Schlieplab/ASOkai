#!/usr/bin/env python
"""
Filename: tests/unit/test_transcript_site.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Version: 0.1.1
Description: Serialization tests for TranscriptSite.
License: LGPL-3.0-or-later
"""

from Bio.Seq import Seq
from GenomeUtils.Genome import TranscriptLocus
import pytest

from ASOkai.Sites import TranscriptSite


@pytest.fixture
def transcript_site() -> TranscriptSite:
    return TranscriptSite(
        id="shared-site",
        loci=[
            TranscriptLocus("ENST00000001", 10, 14),
            TranscriptLocus("ENST00000002", 30, 34),
        ],
        sequence=Seq("ACGT"),
    )


@pytest.mark.unit
@pytest.mark.serialization
def test_transcript_site_serializes_loci_as_plain_json(transcript_site):
    data = transcript_site.to_dict()

    assert data == {
        "__class__": "TranscriptSite",
        "__module__": "ASOkai.Sites._transcript_site",
        "id": "shared-site",
        "loci": [
            {
                "transcript_id": "ENST00000001",
                "start": 10,
                "end": 14,
            },
            {
                "transcript_id": "ENST00000002",
                "start": 30,
                "end": 34,
            },
        ],
        "sequence": "ACGT",
    }


@pytest.mark.unit
@pytest.mark.serialization
def test_transcript_site_reconstructs_transcript_loci():
    site = TranscriptSite.from_dict(
        {
            "__class__": "TranscriptSite",
            "__module__": "ASOkai.Sites._transcript_site",
            "id": "site",
            "loci": [
                {
                    "transcript_id": "ENST00000001",
                    "start": 10,
                    "end": 14,
                }
            ],
            "sequence": "ACGT",
        }
    )

    assert site.loci == [TranscriptLocus("ENST00000001", 10, 14)]
    assert isinstance(site.loci[0], TranscriptLocus)


@pytest.mark.unit
@pytest.mark.serialization
def test_transcript_site_roundtrip_preserves_shared_loci(transcript_site):
    reconstructed = TranscriptSite.from_dict(transcript_site.to_dict())

    assert reconstructed == transcript_site
    assert reconstructed.sequence == transcript_site.sequence
