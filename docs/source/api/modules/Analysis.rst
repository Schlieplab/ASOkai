Analysis
========

The :mod:`ASOkai.Analysis` module defines the base classes used to implement
computational analyses in ASOkai.

:class:`Analysis` is an abstract base class and is not used directly.
Every concrete analysis must inherit from one of its three scope-specific
subclasses:

- :class:`SiteSpecificAnalysis`: use when the analysis only needs information
  available from an individual site.
- :class:`TargetSpecificAnalysis`: use when the analysis needs access to the
  associated target as well as its sites.
- :class:`GenomeWideAnalysis`: use when the analysis needs access to the
  genome, target, and sites.

The classes primarily communicate the scope and context required by an
analysis. For example, :class:`IntrinsicFeaturesAnalysis` inherits from
:class:`SiteSpecificAnalysis` because it computes sequence-derived values for
one site at a time:

.. code-block:: python

   class IntrinsicFeaturesAnalysis(SiteSpecificAnalysis):
       ...

API reference
-------------

.. currentmodule:: ASOkai.Analysis

.. rubric:: Classes

.. automodule:: ASOkai.Analysis
   :members:
   :undoc-members:
   :show-inheritance: