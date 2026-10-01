KMC utilities
=============

ASOkai provides Python wrappers around the external ``kmc`` and ``kmc_tools``
executables. Install ASOkai through the supplied Conda environment when using
these utilities so that both binaries are available on ``PATH``.

.. warning::

   KMC is third-party GPLv3-only software. ASOkai invokes its executables but
   does not distribute or link against KMC. See the third-party software
   section of the project README for licensing details.

Imports
-------

.. code-block:: python

   from ASOkai.Utils import KMC, KMCTools

Running KMC
-----------

``KMC`` accepts the executable name or an explicit executable path. Its
``run`` method follows the KMC command-line interface and returns a completed
subprocess result.

.. code-block:: python

   KMC().run(
       "reads.fastq",
       "counts/sample",
       "work",
       k=25,
       t=8,
   )

Input paths are resolved to absolute paths. Prefix a list file with ``@`` as
required by KMC. Set ``check=True`` to raise ``KMCExecutionError`` when the
process exits unsuccessfully. For KFF output, a path ending in ``.kff`` is
treated as the final filename; KMC receives the corresponding suffix-free
prefix so that it does not produce ``.kff.kff``.

Pipeline integration
--------------------

The built-in ``build-genome-kmer-index`` step creates one durable KFF index
from the downloaded primary-assembly FASTA. It is registered as an independent
step rather than included in the standard workflow before an analysis needs
it. Analyses should reuse that index and batch their query k-mers; short query
passes do not need separate persistent pipeline steps.

The index builder accepts ``--param`` overrides for KMC's memory limit,
FASTA format, strict-memory and homopolymer modes, signature length, count
thresholds, canonicalization, RAM-only mode, bin count, per-stage thread
counts, and output-size optimization. These options also have optional
``parameters.kmc`` configuration keys. The output filename spells out the
resolved options as key/value segments, such as ``.k16.m4.ffm.ci1.``. The
directory already includes the configured assembly, source, and release.
KFF output is fixed for this step; KMC modes that suppress the index are not
available here.

Running kmc_tools
-----------------

``KMCTools`` exposes the ``Simple``, ``Transform``, ``Filter``, and ``Complex``
wrappers. Each builder records an operation and executes it when ``run`` is
called.

.. code-block:: python

   KMCTools.Transform().reduce(
       "valid-kmers",
       ci=2,
   ).dump(
       "valid-kmers.txt",
   ).run(
       "counts/sample",
       t=8,
   )

All wrappers accept ``kmc_tools`` from ``PATH`` by default or an explicit
executable path. Shared execution options include ``t``, ``v``, ``hp``,
``debug``, ``check``, and ``cwd``. Operation-specific options follow the
upstream ``kmc_tools`` command-line interface. When ``check=True``, an
unsuccessful process raises ``KMCTools.KMCToolsExecutionError``.

KMC API
-------

.. autoclass:: ASOkai.Utils.KMC
   :members:
   :show-inheritance:

.. autoexception:: ASOkai.Utils.KMCExecutionError
   :members:
   :show-inheritance:

kmc_tools API
-------------

.. autoclass:: ASOkai.Utils.KMCTools.Simple
   :members:
   :show-inheritance:

.. autoclass:: ASOkai.Utils.KMCTools.Transform
   :members:
   :show-inheritance:

.. autoclass:: ASOkai.Utils.KMCTools.Filter
   :members:
   :show-inheritance:

.. autoclass:: ASOkai.Utils.KMCTools.Complex
   :members:
   :show-inheritance:

.. autoexception:: ASOkai.Utils.KMCTools.KMCToolsExecutionError
   :members:
   :show-inheritance:
