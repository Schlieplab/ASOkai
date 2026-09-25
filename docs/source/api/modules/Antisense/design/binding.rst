Binding
===========

Bindings store two sequences and the positions aligned between them. Candidate
bindings reference a therapeutic and a target site by their endpoint IDs; the
binding remains separate from both. The indices are zero-based in sequences
stored 5' to 3', so paired indices run in opposite directions. Missing indices
describe unpaired bases. An siRNA owns a guide-passenger binding, whose first
sequence is the guide and second sequence is the passenger. It needs no endpoint
IDs because the siRNA owns both strands. Bindings are immutable after creation.

.. autoclass:: ASOkai.Antisense.BasePair
   :members:

.. autoclass:: ASOkai.Antisense.Binding
   :members:
   :undoc-members:
   :show-inheritance:
