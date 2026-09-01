Base analysis
=============

``Analysis`` owns iteration and optional shared-memory thread-pool execution.
Concrete analyses implement ``analyze`` through one of the context-specific
subclasses. Parallel implementations treat their analysis context and sites
as read-only.

.. autoclass:: ASOkai.Analysis.Analysis
   :members:
   :undoc-members:
   :show-inheritance:
