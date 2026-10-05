Pipeline components
===================

ASOkai models execution as steps collected into tasks and workflows. External
packages import the stable extension contracts from :mod:`ASOkai.Plugins`.
Built-in ASOkai modules import contracts directly from the internal module
that owns them.

Component hierarchy
-------------------

``Runnable``
   The shared protocol providing a name and description for pipeline
   components.

``Step``
   One atomic command-line operation. A step owns a ``StepSpec`` and the
   common parsing, output-path, CWL-generation, and execution lifecycle.

``ExternalCommandStep``
   A step whose ``build_command(args)`` method returns an external executable
   and its arguments. The subprocess remains inside the common step lifecycle,
   including producer-side output validation.

``CoreStep``
   A step that downloads, prepares, constructs, or transforms core data.
   These steps usually implement ``run_from_args`` directly.

``UtilityStep``
   A reusable operation on supplied inputs, such as building an index from
   FASTA. Tasks can connect utility inputs to particular producers.

``AnalysisStep``
   A step that runs an ``ASOkai.Analysis.Analysis`` subclass and delegates
   result writing to ``write_results``.

``TableAnalysisStep``
   An ``AnalysisStep`` that writes a primary typed CSV table and optional
   later outputs.

``Task``
   A named CLI-level collection of steps. It may declare named step
   invocations, fixed links, and public output names; older tasks may expose
   ``steps``.

``Workflow``
   A named collection exposing a non-empty sequence of runnable components.
   Its members may be steps, tasks, or other workflows; job planning resolves
   them to the required steps.

Task and workflow compositions are declarations: ASOkai reads their order but
does not modify them. Built-ins therefore use tuples. Plugin components may
use another sequence type, including a list, but should not mutate it after
discovery.

Analysis execution models
-------------------------

``PerUnitAnalysis`` collects zero or more values per unit in input order,
optionally using worker threads. ``BatchAnalysis`` passes the whole unit
collection and thread budget to one backend call. Neither base class fixes
the result type or the number of results per unit. ``AnalysisStep`` runs
either model; ``TableAnalysisStep`` adds the CSV output convention.
``CsvFile`` validates its declared columns and unique index values.

.. _pipeline-step-specification:

The step specification
----------------------

``StepSpec`` is the source of truth for one step's interface. It contains
scalar parameters, file inputs, file outputs, optional applicability rules,
and low-level CWL requirements or hints needed by exceptional steps. Every
concrete step must declare at least one file output so the planner can track
completion and publication. Generated step tools always dispatch through
``ASOkai step <name>``; external executables use ``ExternalCommandStep``
rather than replacing that command.

From this declaration ASOkai derives:

- command-line arguments and parsed values;
- CWL input and output ports;
- configuration paths used by the step;
- dependencies between steps;
- output filenames and publication paths; and
- the generated pipeline-reference documentation.

See :ref:`generated-step-reference` for the declarations used by generated
pages and the schema form for conditional parameter alternatives.

Dependencies are not listed separately. A ``FileInput`` points to a producer
step's exact ``FileOutput`` object, and that connection identifies both the
dependency and the shared file contract.

Scalar parameters
~~~~~~~~~~~~~~~~~

``ScalarParam`` declares a named ``str``, ``int``, ``float``, ``bool``, string
enum, or optional non-boolean scalar value. Its ``config`` path maps the
parameter to a shared fallback in the validated YAML configuration. Defaults
and choices belong in the declaration when they are part of the command-line
contract.
A ``bool`` parameter is a presence flag: it defaults to ``False``, and a true
value emits its option, such as ``--enabled``, without a following value.
Generated CWL represents it as a native Boolean input.

Concrete ``StepRun`` values accept a ``parameters`` mapping of invocation
overrides. Each declared scalar resolves in this order:

1. A value supplied in the invocation's ``parameters`` mapping.
2. The global configuration value at ``ScalarParam.config``, when declared.
3. The declared default, or ``None`` for an omitted optional parameter.

A supplied value overrides the fallback. Supplying ``None`` explicitly clears
a nullable parameter; omitting the parameter uses its fallback. A required
parameter without a value, invalid values, and unknown parameter names are
rejected. Parameters without a ``config`` path use invocation values or their
declared defaults.

For an optional scalar, giving its step CLI flag without a value explicitly
sets it to ``None``. Generated CWL uses this form when clearing a non-null
default. Supplying a value or omitting the flag retains the normal CLI
behavior.

If parameters share a global fallback path, their resolved values must agree;
conflicting values are rejected because output templates use those
configuration paths.

Steps must not declare ``n_threads`` themselves. Every analysis step exposes
the standard ``--n-threads`` argument, resolved from the shared resource
configuration. Per-unit analyses use it for ASOkai's worker pool; batch
analyses receive it in ``analyze_batch`` and manage their own parallelism.
A core step opts in with ``supports_multiple_threads = True`` only when its
runtime consumes ``args.n_threads``.

Configuring runs in YAML
~~~~~~~~~~~~~~~~~~~~~~~~

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
       modality: aso
       mechanism: rnase-h1
       design:
         type: unmodified
   resources:
     default:
       n_threads: 2
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
listed later. An ``id`` is needed only when another run refers to it. A
selected step run's output can be referenced with
``from: run.RUN_ID.OUTPUT_NAME``. To
use an existing file, replace the ``from`` mapping with ``path:
/path/to/target_gene.json``. Relative paths resolve from the current working
directory. A selected run may override its declared scalar parameters using
its own ``parameters`` mapping; a task selection applies matching names to
its children. Fixed values in a task declaration cannot be replaced. Distinct
runs must resolve to distinct output paths, or planning reports a collision.

Invoke ``ASOkai run --configfile config.yaml`` or ``ASOkai export
--configfile config.yaml`` to use these selections. A file with ``runs`` cannot
also use CLI ``--step``, ``--task``, or ``--workflow`` selections. Shared
``genome``, ``target``, and ``antisense`` settings belong under ``parameters``.

Composing task runs
~~~~~~~~~~~~~~~~~~~

Declare ``runs`` on a ``Task`` as ``RunSpec`` objects. Each specification has
a local ``run_id`` and a Step instance, plus optional ``parameters`` and
``inputs``. A ``FromRun`` value names a local child and its declared output,
even if the producer is declared later::

   from ASOkai.Plugins import (
       CreateTargetGeneStep, IntrinsicFeaturesStep, FromRun, RunSpec, Task,
   )

   class TargetAnalysisTask(Task):
       name = "target-analysis"
       description = "Create a target gene and analyze its features."
       runs = (
           RunSpec(
               "features",
               IntrinsicFeaturesStep(),
               inputs={
                   "target_gene": FromRun("gene", "target_gene")
               },
           ),
           RunSpec(
               "gene",
               CreateTargetGeneStep(),
           ),
       )
       outputs = {"target_gene": FromRun("gene", "target_gene")}

For a fixed input file, use ``Path("/data/target_gene.json")`` instead of
``FromRun(...)``. In YAML, use ``path: /data/target_gene.json``.

The planner schedules ``gene`` before ``features``. The ``outputs`` mapping
exposes a stable name to callers; it does not rename the child step's output.
The mapping is optional. A task may omit ``outputs`` and let callers refer to
its child runs directly. A built-in task with ``category = "analysis"`` also
appears in the Analyses documentation index. A task can also declare the same
step more than once, using local IDs to distinguish the runs::

   class CompareRegionsTask(Task):
       name = "compare-regions"
       description = "Create two versions of the target gene."
       runs = (
           RunSpec("exonic", CreateTargetGeneStep(),
                   parameters={"region": "exonic"}),
           RunSpec("transcriptomic", CreateTargetGeneStep(),
                   parameters={"region": "transcriptomic"}),
       )
       outputs = {"target_gene": FromRun("exonic", "target_gene")}

Once registered, this task can receive a task-wide parameter and an override
for one declared child run::

   runs:
     - task: compare-regions
       id: comparison
       parameters:
         k: 21
       runs:
         - id: transcriptomic
           parameters:
             k: 18

``k`` applies to both child runs; the ``transcriptomic`` child uses 18 because
its own ``parameters`` entry takes precedence. Values declared in a task's
``RunSpec.parameters``, such as each child's ``region`` above, are fixed:
task-wide parameters cannot replace them, and an attempted child override is
rejected. Prefer task-wide settings for routine use. Child overrides remain
available for targeted variation; runs with different inputs can share a
destination and therefore cannot execute together in one plan unless their
destinations differ. Nested ``runs`` must name IDs already declared by the task. They
can supply inputs left open by its ``RunSpec`` declarations, but cannot replace
a task-declared input link. Thus the ``features`` to ``gene`` link above is
part of the task's wiring. A link inside a task uses a local child ID such as
``gene``. Outside a named task selection, callers can use a public alias such
as ``from: run.comparison.target_gene`` or address a child output directly,
such as ``from: run.comparison.transcriptomic.target_gene``. The latter uses
the task selection ID, child run ID, and child output name, and works even
when the task does not expose that output through ``Task.outputs``. Omit
``inputs`` when no explicit link is needed. Each distinct run must have a
distinct output destination. Older tasks with ``steps`` remain valid. The
planner converts YAML and CLI selections into ``RunSpec`` objects, then
resolves them into concrete ``StepRun`` objects.

How an input source is chosen
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

An ``inputs`` entry on a selected step run chooses either ``from:`` (a named
run's output) or ``path:`` (an existing file). A task can fix a child's input
in its ``RunSpec.inputs`` declaration. If it does, a nested ``runs`` override
for that input is rejected; otherwise the nested override may supply the
child's ``from:`` or ``path:`` source. A task selection has no separate
``inputs`` mapping.

If the input has no run-level source, shared configuration at
``steps.STEP.inputs.INPUT`` can supply either ``path:`` or ``from:``.
Otherwise, ``FileInput.source`` identifies the step's default producer
output. An input with neither a supplied source nor a default producer
fails planning. Scalar
``parameters`` determine how a producer run executes and where its output
belongs; they do not identify a producer run by themselves. The planner
reuses a valid existing producer output or schedules that producer before
the consumer. With ``--non-recursive``, a missing dependency causes an error
instead of being scheduled.

Configuring runs on the command line
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

CLI selections use the same ordered run declarations and validation as YAML.
The CLI reads ``./config.yaml`` when present, including for CLI-selected runs.
Use ``--configfile`` to select another file. For a CLI-only run, use
``--no-config``; if no default file exists, CLI selections also work without
that flag. Both cases use ``./data`` as the data directory. A file containing
``runs`` cannot be combined with CLI selections. Put shared parameter overrides
before the first selection and run-specific overrides after the step or task
they belong to::

   ASOkai run --configfile common.yaml \
     --param genome.assembly=GRCh39 \
     --step create-target-gene --id reference-gene --param target.region=pre-mrna \
     --step generate-therapeutic-candidates --id candidates \
       --from-run target_gene=reference-gene.target_gene \
     --task compare-regions --id comparison --param target.k=21 \
       --child transcriptomic --param target.k=18

``--id`` names the preceding step or task. Unnamed CLI selections use the step
or task name, with ``-2``, ``-3``, and so on for repeats. Before the first selection,
``--param PATH=VALUE`` sets a shared parameter such as ``genome.assembly``;
the ``parameters.`` prefix is omitted. After a selection, the same path form
applies to that run, or to the child named by the most recent ``--child``.
Run-specific values take precedence over shared values. Values use YAML scalar
syntax, so ``target.k=21`` is an integer. Use ``--from-run
INPUT=RUN_ID.OUTPUT`` for a named producer and ``--input-path INPUT=PATH`` for
an existing file. These options configure the current step or task child;
``--child`` names an ID already declared in the task. A new ``--step`` or
``--task`` starts the next top-level run. ``--workflow`` expands its members
at its position in the CLI sequence. ``export`` accepts the same run options.

File contracts
~~~~~~~~~~~~~~

``FileOutput`` combines a name, an ``OutputPathTemplate``, and a ``FileType``.
The file type owns serialization and validation:

``FileType``
   An unstructured file contract for cases where ASOkai only manages a path.

``JsonFile``
   A JSON contract backed by a serializable class. Its recursively generated
   schema validates nested serializable objects, scalar fields, sequences,
   mappings, and permitted extra serializable keyword arguments.

``CsvFile``
   A table contract with ordered index and data columns. Every column declares
   one scalar type. A table contains every index column and a non-empty subset
   of its declared data columns. Reading and writing validate the header,
   scalar values, consistent rows, and index uniqueness.

``KffFile``
   A binary K-mer File Format contract. Validation first checks the opening
   and closing KFF markers, then makes ``kmc_tools`` read the complete index
   by dumping it to the operating system's null device. The scan uses one
   thread and does not load the index into Python memory or retain the dump.

``FastaFile(gzip=True)`` declares a compressed FASTA output, while
``FastaFile()`` defaults to ``gzip=False`` and declares plain FASTA.
``FastaFile(gzip=None)`` accepts either format as an input contract.
The file contract checks that a path is a file and leaves content parsing to
the consuming tool.

``FileInput`` points to a source ``FileOutput`` and therefore inherits its
file type. A reusable step can instead declare a typed input without a fixed
producer, for example ``FileInput("reference", file_type=FastaFile())``.
This input requires a selected path or producer run. Named producer outputs
must match the declared file type, including FASTA compression. An input with
a fixed source accepts named runs of that exact output. Every input also has
a shared ``path:`` or ``from:`` configuration option. ``path:`` substitutes
an existing file; ``from:`` links a named run. ASOkai validates external files
before running them.

.. _configuring-an-input-producer:

Choosing the producer run for an input
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Normally, a ``FileInput`` receives the producer output made with the main
configuration. This is the default for core and analysis steps alike.

A selected producer run can use different parameters and provide one input
to a consumer::

   runs:
     - step: create-target-gene
       id: comparison
       parameters:
         region: pre-mrna
     - step: example-analysis
       inputs:
         target:
           from: run.comparison.target_gene

The consumer's other inputs continue to use their declared default producers.
Runs with the same step, resolved scalar values, and file inputs share one
execution. Runs that differ in any of those values remain separate.

For an existing file, select ``path:`` on the consuming run::

   runs:
     - step: example-analysis
       inputs:
         target:
           path: /path/to/target_gene.json

Shared configuration also accepts ``steps.example-analysis.inputs.target.path``
or ``steps.example-analysis.inputs.target.from``.

Without an explicit input selection or shared input source, a fixed-source input
uses the producer's main configuration.

Output destinations read configuration values through ``TemplateField``
without requiring a runtime ``ScalarParam``. A run inherits resolved parameter
values from linked producer runs before resolving its own parameters and output
paths. If inputs disagree on a value the consumer needs, planning rejects the
ambiguous mapping. ``InputConfigField`` selects a specific input's configuration
when a step intentionally combines differently configured inputs. For an
existing path, where no producer run exists, it reads the consumer's shared
configuration plus that run's own parameter overrides and defaults.

Output templates can include a step's own content-changing parameters so
indexes built with different options have distinct destinations. Parameters
that only affect execution, such as resource allocation, do not belong in the
destination. Upstream parameters need not be copied into a consumer's filename.

For steps whose output keeps one destination across input changes, validation
receipts include the selected file input or producer run in the run signature.
With the default ``signature`` validation mode, changing an input schedules a
rebuild at that destination. Separate runs that would publish to the same
destination in one plan are still rejected.

Shared step lifecycle
---------------------

When a step command runs, the base class builds its parser from ``StepSpec``
and parses scalar and file arguments. It then validates the standard parallel
worker count and calls ``validate_parameters`` for relationships between
parsed scalar values. Only after validation succeeds does it create output
directories and call ``run_from_args``. Typed file inputs have already been
deserialized and validated by that point.

The pipeline planner uses the same declaration to resolve configuration,
connect producer outputs to consumer inputs, generate CWL, determine final
output paths, and publish results. A step should not reproduce any of this
logic.

Step logging
~~~~~~~~~~~~

Step implementations should emit plain log messages without embedding their
own name. The internal dispatcher prefixes every non-empty line with
``[step:<name>]``. Runner messages instead identify the selected orchestration
level with ``[step:<name>]``, ``[task:<name>]``, or ``[workflow:<name>]``.

Generated-output validation receipts
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Each step fully validates every declared output immediately after producing
it and before reporting success, so invalid files cannot be passed to a
downstream step. After CWL publishes those validated outputs, ASOkai records
one validation receipt for the complete output set under
``datadir/.asokai/validation``. Publication verifies that every destination
exists but does not repeat content validation. A later plan reuses the run
only when its configuration identity, output destinations, and every recorded
file match that receipt. A missing or changed output invalidates the complete
run rather than only one file.

ASOkai does not adopt existing outputs that have no receipt. It reruns the
step, validates its newly produced outputs, publishes them, and creates the
receipt only after successful execution. User-supplied ``path`` files
never receive receipts; they continue to receive their inherited
file-contract validation directly.

The ``validation.existing_outputs`` mode controls this reuse check:

* ``signature`` (the default) requires a matching validation receipt and
  recorded output metadata.
* ``contract`` bypasses receipts during planning and fully validates every
  existing generated output before deciding whether to reuse it.

The selected mode does not change override handling. Successful runs write
receipts in either mode, so changing back to ``signature`` does not require
another run.

Receipts support work reuse and ordinaryfile change detection; 
they are not cryptographic proof against a user who can modify 
both data and receipt files.

.. _analysis-step-lifecycle:

Analysis-step lifecycle
-----------------------

An ``AnalysisStep`` uses ``analysis_kwargs(args)`` for constructor context,
``analysis_units(args)`` for units, and passes ``n_threads`` to the
analysis. It then calls ``write_results(args, analysis, results)`` to write
the declared outputs. ``TableAnalysisStep`` implements that hook with a
tabular convention:

1. its first output is the primary typed CSV;
2. analyses return complete rows, including every index column;
3. optional later outputs receive values from
   ``additional_output_values``; and
4. every value is written through its declared file contract.

This keeps table contributions declarative. Other analysis results can be
written by implementing ``write_results`` on an ``AnalysisStep`` subclass.

.. _pipeline-validation-boundaries:

Validation boundaries
---------------------

Different declarations validate different boundaries:

- ``config.schema.yaml`` validates configuration structure and scalar values;
- ``StepSpec`` validates the step declaration and generated interface;
- file types validate serialized inputs and outputs;
- ``compatible_with`` validates biological applicability when a step is
  selected; and
- pipeline-component validation checks declarations, dependencies, and
  composition for both built-ins and plugins; and
- plugin discovery additionally validates entry points, component types, and
  configuration-schema ownership.

``Step.validate_parameters`` is reserved for relationships between resolved
scalar parameters that cannot be expressed clearly in YAML Schema. It should
not repeat type, choice, required-field, or file-contract validation.

See the :doc:`analysis contribution guide <Analysis-guide>` for the copyable
starting point, and the :doc:`pipeline reference <../../steps/index>` for the
contracts of the built-in steps.
