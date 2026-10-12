Getting started
===============

This guide runs the built-in ``standard`` workflow end to end on one target
gene, then runs a single step and exports a run instead of executing it. It
assumes ASOkai is already :doc:`installed <installation>`.

Configure a run
---------------

ASOkai reads ``config.yaml`` from the working directory. Start from the
maintained example:

.. code-block:: bash

   cp examples/config.example.yaml config.yaml

The example configures a complete run and is commented throughout. Four
sections matter at the start:

``datadir``
   Where every generated file is written. Defaults to ``./data``.

``parameters``
   What to design against: the genome assembly and release, the target gene
   and target-site length ``k``, and the antisense modality and its design.
   The example targets KRAS (``ENSG00000133703``) on GRCh38 with 16-mer sites
   and a 3-10-3 gapmer.

``resources``
   Per-step worker counts and memory. ``default`` applies to every step, and a
   step name overrides it for that step alone. Raising ``n_workers`` is what
   makes an analysis use more than one core.

``runs``
   An explicit ordered selection, commented out in the example. Leave it out
   and select what to run on the command line instead, as below.

No entry under ``parameters`` belongs to one step. Each step reads the keys it
declares, so one file configures the whole pipeline.

See what is available
---------------------

The catalog is generated from the installed package, so it matches the
installed version and includes any installed plugins:

.. code-block:: bash

   asokai list steps
   asokai list tasks
   asokai list analyses
   asokai list workflows

``describe`` shows one unit's configuration keys, inputs, outputs, and
dependencies. Add ``-v`` for the full detail:

.. code-block:: bash

   asokai describe workflow standard
   asokai describe step create-target-gene
   asokai describe analysis compute-intrinsic-features

Preview before running
----------------------

``--dry-run`` resolves the selection and prints what would execute, without
running anything:

.. code-block:: bash

   asokai run --workflow standard --dry-run

.. code-block:: text

   [run] Dry run: 4 steps would execute:

   [run]   1. instantiate-target-gene.genome (download-genome)
   [run]      Parameters:
   [run]        assembly: GRCh38
   ...
   [run]   4. compute-intrinsic-features
   [run]      Inputs:
   [run]        target_gene <- runs.instantiate-target-gene.gene.target_gene
   [run]      Resources:
   [run]        workers: 4

Each step lists the parameters resolved for it from the configuration, and
each input names the run that produces it. The listing is the resolved plan,
so a parameter or dependency that did not resolve as intended is visible
before anything executes.

Run it
------

.. code-block:: bash

   asokai run --workflow standard

Outputs are written under ``datadir`` in a hierarchy derived from the
configuration, so runs with different parameters do not overwrite each other.
A step whose outputs already exist is skipped; ``--force`` re-runs it anyway.

The first run downloads a genome and builds indexes, and takes considerably
longer than later runs.

Run one step or task
--------------------

The same command selects smaller units, and the flags can be repeated and
combined:

.. code-block:: bash

   asokai run --step download-genome
   asokai run --task instantiate-target-gene
   asokai run --step generate-therapeutic-candidates --step compute-intrinsic-features

Dependencies of a selected step run first. ``--non-recursive`` requires them
to exist already and fails when they do not, instead of running them:

.. code-block:: bash

   asokai run --step compute-intrinsic-features --non-recursive

Override configuration per run
------------------------------

``--param`` sets a configuration value for one invocation. Before a selection
it applies to every selected unit; after a selection it applies to that unit
alone:

.. code-block:: bash

   asokai run --param genome.assembly=GRCh38 --step create-target-gene --param target.k=18

``--config-file`` points at another file, and ``--no-config`` ignores
``config.yaml`` entirely and uses only what the command line supplies.

Export instead of running
-------------------------

``export`` writes the selected runs as a CWL job bundle instead of executing
them, for running on a cluster or under another workflow engine:

.. code-block:: bash

   asokai export --workflow standard --recursive

The bundle lands under ``datadir/jobs``. ``--recursive`` includes the
producers the selection needs; without it the bundle refers to existing
outputs by absolute path and runs only where those files already are.

:doc:`Running the pipeline <running/index>` describes the bundle and how to
run it.

Next steps
----------

* :doc:`Steps <steps/index>`, :doc:`tasks <tasks/index>`, and
  :doc:`workflows <workflows/index>` document every built-in unit's runtime
  contract.
* :doc:`Analyses <analyses/index>` lists what the pipeline calculates.
* The :doc:`contributor guide <contributor-guide/index>` covers adding a new
  analysis or step.
