Running the pipeline
====================

A run selects steps, tasks, or a workflow, resolves their parameters and
inputs, and executes the resulting plan. Selections come from a configuration
file, from the command line, or from both. The :doc:`Getting Started
<../getting-started>` guide covers the common path; this page describes the
full selection model.

Configuring runs in YAML
------------------------

A config file selects ordered runs below the root ``runs`` key. Shared
fallbacks live below root ``parameters``; ``resources`` and the optional
output-reuse ``validation`` setting are also root keys. For example::

   datadir: ./data
   parameters:
     genome:
       assembly: GRCh38
       release: 114
       source: ensembl
       species: Homo_sapiens
     target:
       target_name: KRAS
       k: 16
       region: pre-mrna
     antisense:
       modality:
         type: aso
         mechanism: rnase-h1
         design:
           type: unmodified
   resources:
     default:
       n_workers: 2
       memory_mb: 4096
   validation:
     existing_outputs: signature
   runs:
     - step: compute-intrinsic-features
       inputs:
         target_gene:
           from: run.analysis.target_gene
     - task: instantiate-target-gene
       id: analysis

``analysis`` names the task selection. The task declares a public
``target_gene`` output, so the step can refer to it even though the task is
listed later.

Run IDs
   Without an explicit ``id``, selections use their step or task name, and
   repeated selections receive ``-2``, ``-3``, and so on. Explicit IDs are
   reserved before unnamed runs are assigned theirs. Configuration error paths
   name these IDs in place of run indices, even when schema validation fails. These
   IDs also label the log output, as ``[step:create-target-gene]`` or
   ``[task:<name>]``, and a task's children carry the task selection's ID.

Inputs
   ``from: run.RUN_ID.OUTPUT_NAME`` references a selected run's output, and
   ``path: /path/to/target_gene.json`` substitutes an existing file instead.
   Relative paths resolve from the current working directory.

Parameters
   A selected run overrides its declared scalar parameters through its own
   ``parameters`` mapping, using the same nested groups as the shared
   configuration.

Selecting the same step twice, each with its own region, therefore
corresponds to::

   ASOkai run --step create-target-gene --param target.region=exonic \
              --step create-target-gene --param target.region=transcriptomic

and to::

   runs:
     - step: create-target-gene
       parameters:
         target:
           region: exonic
     - step: create-target-gene
       parameters:
         target:
           region: transcriptomic

The second selection is unnamed, so it receives the ID
``create-target-gene-2``.

A run's own values are checked exactly like shared ``parameters`` and
``--param`` overrides, against the same types and the same allowed values.

Every run must write to its own destination. Two runs that resolve to the same
output path are rejected when the plan is built.

Invoke ``ASOkai run --configfile config.yaml`` or ``ASOkai export
--configfile config.yaml`` to use these selections. A file with ``runs`` cannot
also use CLI ``--step``, ``--task``, or ``--workflow`` selections. Shared
``genome``, ``target``, and ``antisense`` settings belong under ``parameters``.

Resources
---------

``resources`` sets how much of the machine each step may use. Entries below
``default`` apply to every step, and a step name overrides them for that step
alone::

   resources:
     default:
       n_workers: 1
       memory_mb: 4096
     identify-potential-repeated-sites:
       n_workers: 16

A step entry merges with ``default`` one key at a time, so the step above
keeps the shared 4096 MB. Without a ``resources`` block, every step uses one
worker and 4096 MB.

``n_workers``
   How many workers the step may use, and the CWL ``coresMin`` request it
   exports with. Only steps that parallelize their work accept it: every
   analysis step, ``build-kmc-index``, and ``build-bowtie2-index``. Naming any
   other step is a configuration error, while a value under ``default`` is
   ignored by the steps that cannot use it.

``memory_mb``
   Memory the step is given, exported as the CWL ``ramMin`` request.
   ``build-kmc-index`` also reads the value directly, to size its own buffers.

Raising ``n_workers`` is what makes a step use more than one core. A per-unit
analysis spreads its units across that many workers; a batch analysis passes
the count to the program it drives. Analyses that use worker processes need
``fork``, so on other platforms they use worker threads instead, which
produces the same results and takes longer.

Output reuse
------------

A step whose outputs already exist is skipped, and ``--force`` runs it anyway.

ASOkai records one validation receipt per completed run, below
``datadir/.asokai/validation``. A later plan reuses the run only when its
configuration, its output destinations, and every recorded file match that
receipt. A missing or changed output invalidates the whole run rather than one
file, so the step runs again.

Outputs without a receipt are never adopted. ASOkai reruns the step and writes
the receipt only once it succeeds. Files supplied with ``path:`` never receive
receipts and keep their file-contract validation instead.

``validation.existing_outputs`` chooses how existing outputs are checked::

   validation:
     existing_outputs: signature

``signature``
   The default. Requires a matching receipt and recorded output metadata.

``contract``
   Ignores receipts and fully validates every existing output before deciding
   whether to reuse it.

Successful runs write receipts in either mode, so switching back to
``signature`` does not require another run.

Receipts detect ordinary file changes and support work reuse. They are not
cryptographic proof against someone able to modify both the data and the
receipts.

Configuring runs on the command line
------------------------------------

CLI selections use the same ordered run declarations and validation as YAML.
The CLI reads ``./config.yaml`` when present, including for CLI-selected runs.
Use ``--configfile`` to select another file. For a CLI-only run, use
``--no-config``; if no default file exists, CLI selections also work without
that flag. Both cases use ``./data`` as the data directory. A file containing
``runs`` cannot be combined with CLI selections. Put shared parameter overrides
before the first selection and run-specific overrides after the step or task
they belong to::

   ASOkai run --configfile common.yaml \
     --param genome.assembly=GRCh38 \
     --step create-target-gene --id reference-gene --param target.region=pre-mrna \
     --step generate-therapeutic-candidates --id candidates \
       --input target_gene=from:run.reference-gene.target_gene \
     --task find-repeated-sites --id repeats \
       --child search --param analysis.potential_repeated_sites.max_ddg=3.0

Each option applies to the selection it follows:

``--id NAME``
   Names the preceding step or task. Unnamed selections use the step or task
   name, with ``-2``, ``-3``, and so on for repeats.

``--param PATH=VALUE``
   Before the first selection, sets a shared parameter such as
   ``genome.assembly``; the ``parameters.`` prefix is omitted. After a
   selection, the same path form applies to that run, or to the child named by
   the most recent ``--child``. Run-specific values take precedence over shared
   values. Values use YAML scalar syntax, so ``target.k=21`` is an integer.

``--input INPUT=from:run.RUN_ID.OUTPUT``
   Links the input to a named producer run.

``--input INPUT=path:PATH``
   Substitutes an existing file. Both forms match the YAML ``from`` and
   ``path`` input declarations. Repeat ``--input`` for several inputs, and
   quote the assignment when a path contains spaces.

``--child ID``
   Names an ID the task already declares, so that later ``--param`` and
   ``--input`` options configure that child.

``--step NAME`` / ``--task NAME``
   Starts the next top-level run.

``--workflow NAME``
   Expands its members at its position in the sequence.

``export`` accepts the same run options.


.. _configuring-an-input-producer:

Configuring task runs
---------------------

A task declares its child runs and their IDs; ``asokai describe task <name>``
lists them. The ``find-repeated-sites`` task declares ``gene``, ``index``, and
``search``.

A task selection sets parameters for the whole task, and a nested ``runs``
entry overrides them for one child::

   runs:
     - task: find-repeated-sites
       id: repeats
       parameters:
         analysis:
           potential_repeated_sites:
             max_ddg: 5.0
       runs:
         - id: search
           parameters:
             analysis:
               potential_repeated_sites:
                 max_ddg: 3.0

The ``search`` child uses 3.0, because its own entry takes precedence over the
task-wide value.

What a selection may override:

* Task-wide parameters reach every child that declares them. Prefer them for
  routine use.
* A child entry under nested ``runs`` overrides them for that child alone, and
  must name an ID the task already declares.
* Values the task fixes in its own declaration cannot be replaced, and an
  attempted child override is rejected.
* A selection can supply inputs the task left open, but cannot replace a link
  the task declared. Omit ``inputs`` when no link is needed.

A task's outputs can be referred to in two forms:

``from: run.repeats.potential_repeated_sites``
   A public output the task declares, as listed by ``asokai describe task``.

``from: run.repeats.search.potential_repeated_sites``
   A child output addressed directly, by task selection ID, child run ID, and
   output name. This form works even when the task does not declare that
   output publicly.

Each distinct run needs its own output destination. Runs that differ only in
their inputs can resolve to the same destination, and then cannot execute
together in one plan.

Connecting inputs
-----------------

An ``inputs`` entry on a selected step run chooses either ``from:`` (a named
run's output) or ``path:`` (an existing file).

By default an input receives the producer output made with the main
configuration, for core and analysis steps alike.

A selected producer run can use different parameters and provide one input
to a consumer::

   runs:
     - step: create-target-gene
       id: exonic-gene
       parameters:
         target:
           region: exonic
     - step: compute-intrinsic-features
       inputs:
         target_gene:
           from: run.exonic-gene.target_gene

The consumer's other inputs continue to use their declared default producers.
Runs with the same step, resolved scalar values, and file inputs share one
execution. Runs that differ in any of those values remain separate.

For an existing file, select ``path:`` on the consuming run::

   runs:
     - step: compute-intrinsic-features
       inputs:
         target_gene:
           path: /path/to/target_gene.json

Shared configuration also accepts
``steps.compute-intrinsic-features.inputs.target_gene.path`` or
``steps.compute-intrinsic-features.inputs.target_gene.from``.

Without an explicit input selection or shared input source, a fixed-source input
uses the producer's main configuration.

A task can fix a child's input
in its own declaration. If it does, a nested ``runs`` override
for that input is rejected; otherwise the nested override may supply the
child's ``from:`` or ``path:`` source. A task selection has no separate
``inputs`` mapping.

If the input has no run-level source, shared configuration at
``steps.STEP.inputs.INPUT`` can supply either ``path:`` or ``from:``.
Otherwise the step's declared default producer supplies it. An input with
neither a supplied source nor a default producer fails planning.

Scalar ``parameters`` decide how a producer run executes and where its output
belongs, but they do not by themselves identify which run produces an input.

The planner reuses a valid existing producer output, or schedules that
producer before the consumer. With ``--non-recursive``, a missing dependency
is an error instead.

Exporting a run
---------------

``asokai export`` writes the selected runs as a CWL job bundle instead of
executing them. The bundle runs on a cluster or under another workflow engine,
and ``run.cwl`` can also be wired into a parent CWL workflow as a subworkflow.
It accepts the same selections and overrides as ``run``:

.. code-block:: bash

   asokai export --workflow standard
   asokai export --step compute-intrinsic-features --recursive

The bundle is written to a timestamped directory below ``datadir/jobs``, such
as ``data/jobs/asokai-export-20261012-113717``. ``--outdir`` chooses another
location.

``export`` includes only the selected runs, where ``run`` is the opposite and
runs missing dependencies unless told not to. Without ``--recursive``, a
producer's output is referenced as an absolute path on the machine that
generated the bundle::

   create-target-gene.target_gene:
     class: File
     path: /home/me/project/data/GRCh38/ensembl/114/targets/.../target.json

That bundle runs only where those files exist at those paths. With
``--recursive`` the producers are generated into the bundle as well, so it
builds everything it needs. Use ``--recursive`` for a bundle that leaves the
machine, and omit it to run one step against outputs already in place.

The bundle contains:

``run.cwl``
   The top-level workflow. Its declared inputs and outputs are the interface a
   parent CWL workflow wires.

``job.yml``
   Resolved parameters and input files for this run.

``steps/*.cwl``
   One generated command-line tool per step run.

``publish.cwl``
   The final tool, which publishes every planned output.

``output-layout.yml``
   Each output's destination, relative to the chosen output directory.

``README.md``
   How to run this particular bundle.

ASOkai must be installed on the machine that runs the bundle, because the
generated tools call ASOkai command-line entry points. The external programs
the selected steps need must also be available there.

A bundle is prepared for one executor, named by ``--executor`` and recorded in
its ``README.md``. The default is ``cwltool``:

.. code-block:: bash

   cwltool --outdir /path/to/data run.cwl job.yml

``--executor toil`` prepares the same bundle for ``toil-cwl-runner`` instead.
The output directory receives the hierarchy described by
``output-layout.yml``. Files at declared destinations may be replaced;
unrelated files below that directory are kept.
