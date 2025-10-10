from typing import TYPE_CHECKING, List
from Bio.Seq import Seq
from .site import Site
from .genomic_site import GenomicSite

if TYPE_CHECKING:
    from GenomeUtils.Genome import Transcript  # type: ignore

class TranscriptSite(Site):
    """Transcript-anchored site defined in cDNA coordinates.

    Represents a region on a specific spliced transcript
    """

    def __init__(self,
                 transcript_id: str,
                 cdna_start: int,
                 cdna_end: int,
                 sequence: Seq,
                 id: str = None,
                 **kwargs):
        """
        Initializes a TranscriptSite object.

        Args:
            transcript_id: Identifier of the transcript this site belongs to.
            cdna_start: 0-based inclusive start position on the transcript.
            cdna_end: 0-based exclusive end position on the transcript.
            sequence: Spliced sequence of the site.
            id: The ID of the site.
            kwargs: Additional keyword arguments.
        """
        self.transcript_id = transcript_id
        
        if id is None:
            id = f"{transcript_id}:{cdna_start}-{cdna_end}"
        self.id = id
        
        self.start = cdna_start
        self.end = cdna_end
        
        Site.__init__(self, sequence=sequence, id=id, **kwargs)

    def to_genomic(self, transcript: "Transcript") -> List[GenomicSite]:
        pass






