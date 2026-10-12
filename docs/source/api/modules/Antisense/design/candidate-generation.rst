Candidate generation
====================

Generators construct candidate therapeutics from target sites.
Antisense therapeutics derive their IDs from the design, independent of any
target site. Generated IDs begin with ``aso:``, ``gapmer:``, or ``sirna:``
and encode the mechanism, layout where applicable, and strand sequences.
Standard ``ACGT`` sequences use two-bit hexadecimal encoding with an explicit
length; other accepted sequences use UTF-8 hexadecimal encoding. Candidate
generation keeps one therapeutic per ID and a separate binding for every
target site, so repeated sequences can share a design without losing sites.
An optional chemistry attached to a strand contributes its ID to that
therapeutic's design ID. The representation of individual nucleotide
modifications remains deferred.

.. autoclass:: ASOkai.Antisense.AntisenseCandidateGenerator
   :members:
   :undoc-members:
   :show-inheritance:

.. autoclass:: ASOkai.Antisense.ASOCandidateGenerator
   :members:
   :undoc-members:
   :show-inheritance:

.. autoclass:: ASOkai.Antisense.GapmerCandidateGenerator
   :members:
   :undoc-members:
   :show-inheritance:

.. autoclass:: ASOkai.Antisense.SiRNACandidateGenerator
   :members:
   :undoc-members:
   :show-inheritance:
