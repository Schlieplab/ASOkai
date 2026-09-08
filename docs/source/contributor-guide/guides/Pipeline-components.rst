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

``AnalysisStep``
   A step that runs an ``ASOkai.Analysis.Analysis`` subclass. Its shared
   implementation owns analysis construction and result serialization.

``Task``
   A named CLI-level collection exposing a non-empty sequence of steps.

``Workflow``
   A named collection exposing a non-empty sequence of runnable components.
   Its members may be steps, tasks, or other workflows; job planning resolves
   them to the required steps.

Task and workflow compositions are declarations: ASOkai reads their order but
does not modify them. Built-ins therefore use tuples. Plugin components may
use another sequence type, including a list, but should not mutate it after
discovery.

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
parameter to a value in the validated YAML configuration. Defaults and choices
belong in the declaration when they are part of the command-line contract.
A ``bool`` parameter is a presence flag: it defaults to ``False``, and a true
value emits its option, such as ``--enabled``, without a following value.
Generated CWL represents it as a native Boolean input.

Steps must not declare ``n_threads`` themselves. Analysis steps support
parallel worker threads by default; a core step opts in with
``supports_multiple_threads = True`` only when its runtime consumes
``args.n_threads``. ASOkai then supplies the standard ``--n-threads`` argument
and resolves its value from the shared resource configuration.

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
   one scalar type. Reading and writing validate the header, scalar values,
   and index uniqueness.

``KffFile``
   A binary K-mer File Format contract. Validation first checks the opening
   and closing KFF markers, then makes ``kmc_tools`` read the complete index
   by dumping it to the operating system's null device. The scan uses one
   thread and does not load the index into Python memory or retain the dump.

``FileInput`` points to a source ``FileOutput`` and therefore inherits its
file type. Every input automatically has a ``path_override`` configuration
option that lets a user substitute an existing file. ASOkai validates that
external override before admitting it to the execution plan.

.. _configuring-an-input-producer:

Choosing the producer run for an input
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Normally, a ``FileInput`` receives the producer output made with the main
configuration. This is the default for core and analysis steps alike.

An input can expose a small, explicit set of producer parameters when a
consumer needs a differently configured producer output::

   target_input = FileInput(
       "target",
       source=CreateTargetGeneStep.target_gene_output,
       configurable_parameters=("region",),
   )

The names in ``configurable_parameters`` are names from the producer's
``StepSpec.params``. Only expose parameters that make biological sense for
that input; this is the contributor-owned boundary for what users may change.
A user can then select the producer configuration below the consuming step::

   steps:
     example-analysis:
       inputs:
         target:
           parameters:
             region: pre-mrna

ASOkai copies the main configuration, changes the selected producer
parameters, and resolves that producer's dependencies recursively. Requests
with the same producer step, resolved scalar values, and file inputs share
one run. Requests that differ in any of those values remain separate.

``path_override`` is the alternative when the required file already exists::

   steps:
     example-analysis:
       inputs:
         target:
           path_override: /path/to/target_gene.json

An input may specify ``parameters`` or ``path_override``, never both. With
neither, it uses the producer's main configuration.

Output destinations read configuration values through ``TemplateField``
without requiring a runtime ``ScalarParam``. ``InputConfigField`` reads a
value from the resolved producer configuration selected for one file input.
For ``path_override``, where no producer run exists, it reads the consumer's
main configuration.

Every parameter that can change an output's contents must be represented in
that output's ``OutputPathTemplate``. Distinct parameter configurations must
resolve to distinct destination paths so that one run cannot overwrite or be
mistaken for another run's output. Parameters that only affect execution,
such as resource allocation, do not belong in the destination.

The same rule applies to an input-specific producer configuration. If that
choice changes a consumer's output contents, add an ``InputConfigField`` for
that input to the consumer's destination. Output identity remains entirely
configuration-driven; ASOkai does not infer it from filenames.

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
receipt only after successful execution. User-supplied ``path_override`` files
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

Every step inherits ``cache_version = 1``. Increment this positive integer
when an implementation change can alter output contents without changing the
declared parameters, inputs, or destinations. This applies to built-in and
plugin steps alike and avoids invalidating unrelated runs when the overall
ASOkai package version changes. Receipts support work reuse and ordinary file
change detection; they are not
cryptographic proof against a user who can modify both data and receipt files.

.. _analysis-step-lifecycle:

Analysis-step lifecycle
-----------------------

An ``AnalysisStep`` adds a stricter convention for tabular site results:

1. its first output is the primary typed CSV with one index column;
2. ``analysis_kwargs(args)`` returns arguments for ``analysis_cls``;
3. the base class supplies ``n_threads`` and runs the analysis;
4. site keys become CSV index values and analysis values become data columns;
5. optional later outputs receive values from
   ``additional_output_values``; and
6. every value is written through its declared file contract.

This keeps ordinary analysis contributions declarative. Custom execution is
appropriate for a ``CoreStep``; it should not be introduced into an analysis
step merely to parse inputs or write results.

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
