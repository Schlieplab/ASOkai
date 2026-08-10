Analysis
========

The :mod:`ASOkai.Analysis` module contains the base classes for computations
performed over target sites.

Choose the narrowest scope that provides the context the calculation needs:

- :class:`~ASOkai.Analysis.SiteSpecificAnalysis` receives individual sites.
- :class:`~ASOkai.Analysis.TargetSpecificAnalysis` also has access to the
  associated target.
- :class:`~ASOkai.Analysis.GenomeWideAnalysis` also has access to the genome.

Concrete analyses implement :meth:`~ASOkai.Analysis.Analysis.analyze` and
return named scalar values for each site. The inherited
:meth:`~ASOkai.Analysis.Analysis.run` method handles iteration and optional
multiprocessing.

API reference
-------------

.. automodule:: ASOkai.Analysis
   :members:
   :undoc-members:
   :show-inheritance:
