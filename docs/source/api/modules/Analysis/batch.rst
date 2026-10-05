Batch analyses
==============

``BatchAnalysis`` passes all analysis units and the configured ``n_threads`` value to
one backend invocation. The concrete analysis controls how it uses that
thread budget. The result type and number of returned values are determined
by the concrete analysis.

.. autoclass:: ASOkai.Analysis.BatchAnalysis
   :members:
   :undoc-members:
   :show-inheritance:
