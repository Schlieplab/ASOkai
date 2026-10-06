Batch analyses
==============

``BatchAnalysis`` passes all analysis units and the configured ``n_workers`` value to
one backend invocation. The concrete analysis controls how it uses that
worker budget. The result type and number of returned values are determined
by the concrete analysis.

.. autoclass:: ASOkai.Analysis.BatchAnalysis
   :members:
   :undoc-members:
   :show-inheritance:

.. autoclass:: ASOkai.Analysis.GenomicHitsAnalysis
   :members:
   :undoc-members:
   :show-inheritance:

.. autoclass:: ASOkai.Analysis.SiteGenomicHits
   :members:
   :undoc-members:
   :show-inheritance:
