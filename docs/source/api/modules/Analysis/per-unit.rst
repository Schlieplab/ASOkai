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

Candidate repeated sites
------------------------

:class:`~ASOkai.Analysis.TreesearchTargetSitesAnalysis` searches each target
site for variants that the site's own gapmer still binds. See
:doc:`/steps/treesearch-target-sites` for the search, its identifiers, and its
output.

.. autoclass:: ASOkai.Analysis.TreesearchTargetSitesAnalysis
   :members:
   :undoc-members:
   :show-inheritance:

.. autoclass:: ASOkai.Analysis.CandidateRepeatedSite
   :members: id, is_reference
   :show-inheritance:
