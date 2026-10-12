Binding
===========

Bindings store two sequences and a compact two-strand dot-bracket structure.
``(`` and ``)`` mark paired positions, ``.`` marks unpaired positions, and
``&`` separates the strands, as in ViennaRNA. For example, ``(((&)))`` pairs
three bases on each strand. ``Binding.pairs`` interprets the structure as
zero-based, antiparallel indices; ``Binding.from_pairs`` performs the reverse
conversion. Candidate bindings reference a therapeutic and a target site by
their endpoint IDs. An siRNA owns a guide-passenger binding and needs no
endpoint IDs. Bindings are immutable after creation.

.. autoclass:: ASOkai.Antisense.BasePair
   :members:

.. autoclass:: ASOkai.Antisense.Binding
   :members:
   :undoc-members:
   :show-inheritance:
