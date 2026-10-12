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

Internal steps are registered ``Step`` instances with ``listed = False``.
They remain available for explicit runs and descriptions; see
:doc:`Internal steps <Internal-steps>` for their contributor-facing references.

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
optionally using worker threads or processes. ``BatchAnalysis`` passes all
units and the configured worker count to one backend call. Neither base class
fixes the result type or the number of results per unit. ``AnalysisStep`` runs
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

Selecting runs, linking inputs to producers, and the command-line
equivalents are described in :doc:`Running the pipeline
</running/index>`.

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

Steps must not declare ``n_workers`` themselves. Every analysis step exposes
the standard ``--n-workers`` argument, resolved from the shared resource
configuration. Per-unit analyses use it for ASOkai's worker pool; batch
analyses receive it in ``analyze_batch`` and manage their own parallelism.
A core step opts in with ``supports_multiple_workers = True`` only when its
runtime consumes ``args.n_workers``.

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
its child runs directly. Set ``category`` to ``"core"``, ``"analysis"``, or
``"utils"`` to group the task in CLI listings. Built-in tasks use the same
categories in the Tasks documentation index; built-in analysis tasks also
appear in the Analyses index. Tasks without a category appear under Pipeline
in the CLI. A task can declare
the same step more than once, using local IDs to distinguish the runs::

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

Older tasks with ``steps`` remain valid. The
planner converts YAML and CLI selections into ``RunSpec`` objects, then
resolves them into concrete ``StepRun`` objects.

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

Output destinations and input configuration
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

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
``[step:<run-id>]``, using the run ID that
:doc:`Running the pipeline </running/index>` describes.

Generated-output validation receipts
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Each step fully validates every declared output immediately after producing it
and before reporting success, so an invalid file cannot reach a downstream
step. After CWL publishes those validated outputs, ASOkai records one
validation receipt for the complete output set. Publication verifies that
every destination exists but does not repeat content validation.

A step therefore does not check whether its outputs already exist, and does
not decide whether to reuse them. :doc:`Running the pipeline </running/index>`
describes the reuse rules and the ``validation.existing_outputs`` modes that
users configure.

.. _analysis-step-lifecycle:

Analysis-step lifecycle
-----------------------

An ``AnalysisStep`` uses ``analysis_kwargs(args)`` for constructor context,
``analysis_units(args)`` for units, and passes ``n_workers`` to the
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

The shared parameter resolver uses each ``ScalarParam.config`` path to apply
its field schema to resolved configuration values, invocation overrides, and
defaults. Standalone step CLIs use this same resolver after argument parsing.
This checks scalar constraints without requiring unrelated configuration fields;
full configuration validation also checks structure and relationships between
groups.

``Step.validate_parameters`` is reserved for relationships between resolved
scalar parameters that cannot be expressed clearly in YAML Schema. It should
not repeat type, choice, required-field, or file-contract validation.

See the :doc:`analysis contribution guide <Analysis-guide>` for the copyable
starting point, and the :doc:`pipeline reference <../../steps/index>` for the
contracts of the built-in steps.
