Per-unit analyses
=================

``PerUnitAnalysis`` applies a calculation independently to each analysis unit.
Each unit can produce zero or more results. ``run`` preserves input order
with either worker threads or processes.

.. autoclass:: ASOkai.Analysis.PerUnitAnalysis
   :members:
   :undoc-members:
   :show-inheritance:

.. autoclass:: ASOkai.Analysis.IntrinsicFeaturesAnalysis
   :members:
   :undoc-members:
   :show-inheritance:

Similar sequences
-----------------

:class:`~ASOkai.Analysis.SimilarSequenceAnalysis` searches each target site for
sequences that the site's own gapmer still binds. See
:doc:`/steps/potential-repeated-sites` for the search, its identifiers, and its
output.

.. autoclass:: ASOkai.Analysis.SimilarSequenceAnalysis
   :members:
   :undoc-members:
   :show-inheritance:
