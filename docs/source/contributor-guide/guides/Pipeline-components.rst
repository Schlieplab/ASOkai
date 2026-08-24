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

``CoreStep``
   A step that downloads, prepares, constructs, or transforms core data.
   These steps usually implement ``run_from_args`` directly.

``AnalysisStep``
   A step that runs an ``ASOkai.Analysis.Analysis`` subclass. Its shared
   implementation owns analysis construction and result serialization.

``Task``
   A named CLI-level collection of steps.

``Workflow``
   A named collection of runnable components. Its members may be steps,
   tasks, or other workflows; job planning resolves them to the required
   steps.

The step specification
----------------------

``StepSpec`` is the source of truth for one step's interface. It contains
scalar parameters, file inputs, file outputs, optional applicability rules,
and the low-level CWL settings needed by exceptional steps.

From this declaration ASOkai derives:

- command-line arguments and parsed values;
- CWL input and output ports;
- configuration paths used by the step;
- dependencies between steps;
- output filenames and publication paths; and
- the generated pipeline-reference documentation.

Dependencies are not listed separately. A ``FileInput`` points to a producer
step's exact ``FileOutput`` object, and that connection identifies both the
dependency and the shared file contract.

Scalar parameters
~~~~~~~~~~~~~~~~~

``ScalarParam`` declares a named ``str``, ``int``, ``float``, ``bool``, enum,
or optional scalar value. Its ``config`` path maps the parameter to a value in
the validated YAML configuration. Defaults and choices belong in the
declaration when they are part of the command-line contract.

Steps must not declare ``n_processes`` themselves. Analysis steps support
multiprocessing by default; a core step opts in with
``supports_multiple_processes = True`` only when its runtime consumes
``args.n_processes``. ASOkai then supplies the standard process argument and
resolves its value from the shared resource configuration.

File contracts
~~~~~~~~~~~~~~

``FileOutput`` combines a name, an ``OutputPathTemplate``, and a ``FileType``.
The file type owns serialization and validation:

``FileType``
   An unstructured file contract for cases where ASOkai only manages a path.

``JsonFile``
   A JSON contract backed by a serializable class. Its recursively generated
   schema validates nested serializable objects, scalar fields, sequences,
   mappings, and permitted extra scalar keyword arguments.

``CsvFile``
   A table contract with ordered index and data columns. Every column declares
   one scalar type. Reading and writing validate the header, scalar values,
   and index uniqueness.

``FileInput`` points to a source ``FileOutput`` and therefore inherits its
file type. Every input automatically has a ``path_override`` configuration
option that lets a user substitute an existing file. The file is parsed and
validated exactly like the producer's output.

Output destinations use values from declared scalar parameters. A
``TemplateField`` can define how one placeholder is selected or transformed
without adding path-building logic to the step implementation.

Every parameter that can change an output's contents must be represented in
that output's ``OutputPathTemplate``. Distinct parameter configurations must
resolve to distinct destination paths so that one run cannot overwrite or be
mistaken for another run's output. Parameters that only affect execution,
such as resource allocation, do not belong in the destination.

Shared step lifecycle
---------------------

When a step command runs, the base class builds its parser from ``StepSpec``,
parses scalar and file arguments, creates output directories, and calls
``run_from_args``. Typed file inputs have already been deserialized and
validated by that point.

The pipeline planner uses the same declaration to resolve configuration,
connect producer outputs to consumer inputs, generate CWL, determine final
output paths, and publish results. A step should not reproduce any of this
logic.

Analysis-step lifecycle
-----------------------

An ``AnalysisStep`` adds a stricter convention for tabular site results:

1. its first output is the primary typed CSV with one index column;
2. ``analysis_kwargs(args)`` returns arguments for ``analysis_cls``;
3. the base class supplies ``n_processes`` and runs the analysis;
4. site keys become CSV index values and analysis values become data columns;
5. optional later outputs receive values from
   ``additional_output_values``; and
6. every value is written through its declared file contract.

This keeps ordinary analysis contributions declarative. Custom execution is
appropriate for a ``CoreStep``; it should not be introduced into an analysis
step merely to parse inputs or write results.

Validation boundaries
---------------------

Different declarations validate different boundaries:

- ``config.schema.yaml`` validates configuration structure and scalar values;
- ``StepSpec`` validates the step declaration and generated interface;
- file types validate serialized inputs and outputs;
- ``compatible_with`` validates biological applicability when a step is
  selected; and
- plugin discovery validates entry points, component types, dependencies,
  configuration-schema ownership, and composition.

``Step.validate_parameters`` is reserved for relationships between resolved
scalar parameters that cannot be expressed clearly in YAML Schema. It should
not repeat type, choice, required-field, or file-contract validation.

See the :doc:`analysis contribution guide <Analysis-guide>` for the copyable
starting point, and the :doc:`pipeline reference <../../steps/index>` for the
contracts of the built-in steps.
