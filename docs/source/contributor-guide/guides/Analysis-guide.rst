Adding an analysis step
=======================

An analysis contribution has two parts:

1. an analysis class containing the scientific calculation; and
2. a ``TableAnalysisStep`` describing how that calculation produces a CSV
   table in the pipeline.

The step declaration supplies the command-line interface, configuration
mapping, file validation, dependencies, output paths, and generated
documentation. Contributors should only implement behavior specific to the
analysis.

Start from the template
-----------------------

Copy ``examples/contributor_steps/analysis_step.py`` and replace its example
names, calculation, and contracts. The template is kept executable and is
validated with the other contributor steps.

.. literalinclude:: ../../../../examples/contributor_steps/analysis_step.py
   :language: python
   :caption: examples/contributor_steps/analysis_step.py

Implement the calculation
-------------------------

Add the analysis class under ``src/ASOkai/Analysis`` and export it from
``ASOkai.Analysis``. Choose :class:`~ASOkai.Analysis.PerUnitAnalysis` for
independent analysis units or :class:`~ASOkai.Analysis.BatchAnalysis` when a backend
needs the entire collection at once. Declare ``analysis_unit_type`` as ``site``,
``therapeutic``, or ``binding``. A binding unit represents a
therapeutic-site pair; search queries remain internal values.

``Analysis`` defines execution over units without fixing the result type
or the number of values returned per unit. ``AnalysisStep`` runs the
calculation and delegates writing to ``write_results``.
``TableAnalysisStep`` supplies the CSV convention used below.

Provide required scientific context, such as a target or genome, through the
concrete analysis constructor. Units are passed to ``run(units)``.
Implement ``analyze_unit(unit)`` for a per-unit analysis. When used with
``TableAnalysisStep``, it returns zero or more complete row dictionaries, each
including its index columns. The inherited
``run(units, n_threads=...)`` uses shared-memory worker threads and preserves
input order. Parallel implementations must treat shared context and units
as read-only. A batch analysis implements
``analyze_batch(units, *, n_threads)``; it receives the configured thread
count and controls its own parallelism. A binding analysis can pass
therapeutic-site pairs as its units, or return multiple binding rows for a
site when the CSV index identifies each binding uniquely.

Declare the pipeline contract
-----------------------------

An analysis table step inherits from ``TableAnalysisStep`` and declares ``name``,
``description``, ``analysis_cls``, and ``spec``. A built-in step imports each
contract from its owning ``ASOkai._pipeline`` module, as shown in the template.
An independently installed plugin imports the public equivalents from
:mod:`ASOkai.Plugins`.

Use ``StepSpec`` to collect the analysis's ``ScalarParam``, ``FileInput``, and
``FileOutput`` declarations. Their complete ownership and validation rules are
documented in :ref:`pipeline-step-specification`; the analysis guide only adds
the conventions specific to analysis outputs below.

Declare every ``FileOutput`` once as a class attribute and reuse that object
in ``StepSpec.outputs``. Referencing that class attribute from a later
``FileInput`` connects the steps without a separate dependency list.

Configure a producer for one input
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

A file input uses its fixed producer's main configuration by default. To use a
different producer configuration for one input, select a named producer run
and link its output in the consuming run. The
:ref:`configuring-an-input-producer` section shows the YAML selection,
existing-file alternative, sharing behavior, and output-path rule. These
rules apply unchanged to analysis steps.

Analysis outputs
~~~~~~~~~~~~~~~~

The first output of a ``TableAnalysisStep`` is its primary CSV table. Analyses
used with that step return row dictionaries with every declared index column
and at least one declared data column. Data columns may be selected for a run.
The CSV contract writes a header and validates column names, order, scalar
types, consistent rows, and unique index values, including composite indexes.

An analysis table step may declare additional CSV or JSON outputs after its primary
output. When it does, implement ``additional_output_values`` and return a
mapping from each additional ``FileOutput`` object to the value that should be
written. The base class validates and serializes those values.

Connect parsed inputs to the analysis
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Implement ``analysis_units(args)`` to supply analysis units. Override
``analysis_kwargs(args)`` when the concrete analysis needs constructor context.
File arguments are already parsed and validated through
their inherited file contracts. For example, a target-gene JSON input is
available as ``args.target_gene`` containing a ``TargetGene`` object; the
contributor should not open or deserialize it again.

The shared :ref:`analysis-step-lifecycle` constructs the analysis, passes the
configured thread count to its ``run`` method, and writes every declared
output. All analysis steps expose the standard ``--n-threads`` option.

There is no contributor-defined ``main`` function, input-loading hook,
metadata payload, or output-writing hook for a ``TableAnalysisStep``.
For another output format, inherit from ``AnalysisStep`` and implement
``write_results(args, analysis, results)``.

Configuration and validation
----------------------------

For a built-in step, add new configuration fields to
``src/ASOkai/_pipeline/config.schema.yaml`` and document them in
``examples/config.example.yaml``. Reuse existing fields when they already
represent the required value.

The shared schema already defines named run ``parameters`` and ``inputs``
selections, along with ``steps.<consumer>.inputs.<input>.path_override``.
Parameter names and value types come from each step's ``ScalarParam``
declarations.

Follow the :ref:`pipeline-validation-boundaries`: express structural and scalar
constraints in YAML Schema, and override ``validate_parameters(values)`` only
for relationships between resolved scalar parameters that the schema cannot
express clearly.

Use ``StepSpec.compatible_with`` only for real biological applicability
restrictions, such as a mechanism or modality required by the analysis. Omit
it when the analysis is generally applicable.

.. _generated-step-reference:

Generated reference documentation
---------------------------------

The pipeline reference is generated from the same declarations that ASOkai
uses at runtime. Contributors do not maintain a second documentation contract.
The generated page reads the following sources:

``Step.description``
   Introduces the step.

``StepSpec.compatible_with``
   Creates the applicability section when the step has a biological
   restriction.

``ScalarParam`` and ``config.schema.yaml``
   Select the configuration values used by the step and provide their types,
   requirements, constraints, and descriptions.

``FileInput.doc`` and ``FileOutput.doc``
   Describe file dependencies and produced files. Their file types supply the
   format and link JSON outputs to their serializable classes.

``OutputPathTemplate``
   Supplies the documented destination template and example output path.

``CsvFile`` and the analysis class docstring
   Declare output columns and their types. Describe a column in the analysis
   class docstring with one named bullet::

      class ExampleAnalysis(PerUnitAnalysis):
          """Calculate one value for each target site.

          - **example_value**: Length of the target-site sequence.
          """

   The bullet name must match a declared CSV column. Columns without a matching
   bullet remain valid but have no generated meaning beyond their type and
   role.

Conditional parameter alternatives
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

When one configuration value selects between parameter sets, express that
relationship in the YAML schema. The reference renderer recognizes two or
more sibling
``allOf`` branches in which each ``if`` selects one string ``const`` and each
``then`` declares the fields required, allowed, or forbidden for that value.
It renders those alternatives as separate parameter subsections with separate
configuration examples.

For example, this schema separates ``simple`` and ``bounded`` modes without
adding documentation-only declarations:

.. code-block:: yaml

   mode:
     type: object
     additionalProperties: false
     required:
       - type
     properties:
       type:
         type: string
         description: Calculation mode.
       limit:
         type: integer
         minimum: 1
         description: Maximum value used by bounded mode.
     allOf:
       - if:
           required: [type]
           properties:
             type:
               const: bounded
         then:
           required: [limit]
       - if:
           required: [type]
           properties:
             type:
               const: simple
         then:
           not:
             anyOf:
               - required: [limit]

The selector and conditional fields must also be referenced by the step's
``ScalarParam`` declarations; unused schema fields are not added to that
step's page. Other valid YAML-schema conditions still validate configuration,
but the renderer does not turn conditions outside this documented form into
separate subsections. An ``x-error-message`` on such a condition can provide
an ordinary parameter rule instead.

Built-in pages use ``examples/config.example.yaml`` for rendered values and
example paths, so every built-in configuration field should have a realistic
example there.

Plugin documentation
~~~~~~~~~~~~~~~~~~~~

Installed plugins are not inserted into ASOkai's static documentation build.
A plugin owns its own documentation and decides which declarations to publish.
The runtime plugin contract requires the ``asokai.steps`` entry point and, when
the plugin owns configuration, the ``asokai.config_schemas`` entry point; it
does not require Sphinx documentation.

Registration
------------

Built-in analysis steps live in
``src/ASOkai/_pipeline/steps/analysis`` and are added to ``_BUILTIN_STEPS`` in
``src/ASOkai/_pipeline/catalog.py``.

Add a built-in analysis class to the API page matching its execution model:
``docs/source/api/modules/Analysis/per-unit.rst`` or ``batch.rst``. Add an ``autoclass`` entry
for the class exported from ``ASOkai.Analysis``. Add a minimal step page under
``docs/source/steps`` containing ``asokai-step-reference`` with the registered
step name; the directive generates the page contents from the step contract.

An independently installed plugin does not modify ASOkai's registry. It
publishes the step through the ``asokai.steps`` Python entry-point group.
When it introduces configuration fields, it also publishes its YAML schema
through ``asokai.config_schemas``. ASOkai discovers and validates these entry
points from the installed package metadata.

See ``examples/plugins/example_analysis`` for a minimal installable plugin,
including its package layout, entry points, and configuration schema.

Check the contribution
----------------------

Run the focused contributor contract checks while developing:

.. code-block:: console

   pytest -q tests/contributor/test_analysis_steps.py
   pre-commit run validate-asokai-contributor-steps --all-files

Run the full test suite before submitting a change:

.. code-block:: console

   pytest

The pipeline-reference pages are generated from step declarations. Keep those
declarations clear because they are also the documentation source.
