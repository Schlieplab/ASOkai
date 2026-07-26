#!/usr/bin/env python
"""
Filename: src/ASOkai/Sites/_transcript_site.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Version: 0.1.1
Description: This file defines the TranscriptSite class for representing transcript-anchored sites.
License: LGPL-3.0-or-later
"""
from typing import TYPE_CHECKING, List
from Bio.Seq import Seq
from ._site import Site
from ._genomic_site import GenomicSite

if TYPE_CHECKING:
    from GenomeUtils.Genome import Transcript  # type: ignore

class TranscriptSite(Site):
    """Transcript-anchored site defined in cDNA coordinates.

    Represents a region on a specific spliced transcript
    """

    def __init__(self,
                 transcript_id: str,
                 t_start: int,
                 t_end: int,
                 sequence: Seq,
                 id: str | None = None,
                 **kwargs):
        """
        Initializes a TranscriptSite object.

        Args:
            transcript_id: Identifier of the transcript this site belongs to.
            t_start: 0-based inclusive start position on the transcript.
            t_end: 0-based exclusive end position on the transcript.
            sequence: Spliced sequence of the site.
            id: The ID of the site.
            kwargs: Additional keyword arguments.
        """
        self.transcript_id = transcript_id
        
        if id is None:
            id = f"{transcript_id}:{t_start}-{t_end}"
        self.id = id
        
        self.t_start = t_start
        self.t_end = t_end
        
        Site.__init__(self, sequence=sequence, id=id, **kwargs)
    
    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(id='{self.id}', transcript_id='{self.transcript_id}', t_start={self.t_start}, t_end={self.t_end})"

    def validate(self) -> None:
        """Validate a serialized transcript site."""
        super().validate()
        if type(self.transcript_id) is not str or not self.transcript_id.strip():
            raise ValueError("Transcript id must be a non-blank string.")
        if type(self.t_start) is not int or self.t_start < 0:
            raise ValueError(
                "Transcript site start must be a non-negative integer."
            )
        if type(self.t_end) is not int or self.t_end <= self.t_start:
            raise ValueError(
                "Transcript site end must be an integer greater than start."
            )
        if len(self.sequence) != self.t_end - self.t_start:
            raise ValueError(
                "Transcript site sequence length must match its half-open interval."
            )

    def to_genomic(self, transcript: "Transcript") -> List[GenomicSite]:
        raise NotImplementedError
    
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, TranscriptSite):
            return NotImplemented
        return (
            self.id == other.id
            and self.transcript_id == other.transcript_id
            and self.t_start == other.t_start
            and self.t_end == other.t_end
        )




