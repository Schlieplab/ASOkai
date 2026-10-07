ViennaRNA binding energies
==========================

:func:`~ASOkai.Utils.binding_dg` computes the binding free energy of two
strands with the ViennaRNA Python bindings:

.. math::

   \Delta G_\text{binding} = \text{MFE}(\text{first\&second}) -
   (\text{MFE}(\text{first}) + \text{MFE}(\text{second}))

An optional dot-bracket constraint for ``first&second`` enforces selected base
pairs. If the constraint cannot be satisfied, the function raises an error
rather than returning ViennaRNA's placeholder energy. Single-strand energies
are cached per process.

.. code-block:: python

   from ASOkai.Utils import binding_dg

   dg = binding_dg("ATGACTGAATATAAAC", "GTTTATATTCAGTCAT", temperature=37.0)

ViennaRNA applies RNA energy parameters and treats ``T`` as ``U``. For DNA
oligonucleotides, the result approximates an RNA-RNA duplex.

ViennaRNA is third-party software distributed under its own license. ASOkai
imports its Python bindings when an energy is first calculated.

.. autofunction:: ASOkai.Utils.binding_dg
