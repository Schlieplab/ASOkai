Site types
==========

Target extraction assigns ``site:`` IDs from the genome assembly and the site's
1-based inclusive genomic coordinates, including strand. A site that spans a
splice junction lists its genomic segments in transcript order, separated by
``|``. The same physical site keeps its ID across extraction order, target
name versus gene ID, and overlapping target regions. Transcript offsets remain
available in ``TranscriptSite.loci`` but do not define the shared site ID.

.. autoclass:: ASOkai.Sites.Site
   :members:
   :undoc-members:
   :show-inheritance:

.. autoclass:: ASOkai.Sites.GenomicSite
   :members:
   :undoc-members:
   :show-inheritance:

.. autoclass:: ASOkai.Sites.TranscriptSite
   :members:
   :undoc-members:
   :show-inheritance:
