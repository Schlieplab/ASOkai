Adding an analysis step
=======================

An analysis contribution has two parts:

1. an analysis class containing the scientific calculation; and
2. an ``AnalysisStep`` describing how that calculation participates in the
   pipeline.

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
``ASOkai.Analysis``. Choose the narrowest base class that provides the
required context:

- :class:`~ASOkai.Analysis.SiteSpecificAnalysis` for a calculation that only
  needs each site;
- :class:`~ASOkai.Analysis.TargetSpecificAnalysis` when it also needs the
  target; or
- :class:`~ASOkai.Analysis.GenomeWideAnalysis` when it also needs the genome.

Implement :meth:`~ASOkai.Analysis.Analysis.analyze`. It returns a mapping from
column names to scalar values for one site. The inherited
:meth:`~ASOkai.Analysis.Analysis.run` method applies that calculation to all
sites and handles shared-memory worker threads, so contributors normally do
not override it. When more than one worker is configured, ``analyze`` may run
concurrently and must treat its analysis context and sites as read-only.

Declare the pipeline contract
-----------------------------

An analysis step inherits from ``AnalysisStep`` and declares ``name``,
``description``, ``analysis_cls``, and ``spec``. A built-in step imports each
contract from its owning ``ASOkai._pipeline`` module, as shown in the template.
An independently installed plugin imports the public equivalents from
:mod:`ASOkai.Plugins`.

``StepSpec`` contains three kinds of declarations:

``ScalarParam``
   A scalar command-line argument, optionally populated from a dotted
   configuration path.

``FileInput``
   A file produced by another step. Its ``source`` is that step's
   ``FileOutput`` declaration. This connection supplies the dependency and
   file type automatically. A user may provide a pre-existing file through
   ``path_override``.

``FileOutput``
   A produced file, its type, and its destination below the configured data
   directory. ``JsonFile`` validates serializable object structures;
   ``CsvFile`` declares ordered index and data columns with scalar types.

Declare every ``FileOutput`` once as a class attribute and reuse that object
in ``StepSpec.outputs``. Referencing that class attribute from a later
``FileInput`` connects the steps without a separate dependency list.

Configure a producer for one input
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

A file input uses its producer's main configuration by default. Set
``configurable_parameters`` only when that particular input should permit a
user to change selected producer parameters. The
:ref:`configuring-an-input-producer` section shows the declaration, YAML
configuration, path-override alternative, sharing behavior, and output-path
rule. These rules apply unchanged to analysis steps.

Analysis outputs
~~~~~~~~~~~~~~~~

The first output of an analysis step is its primary CSV table. It must have
exactly one index column. The keys returned by ``Analysis.run`` become the
index values, and the values returned by ``analyze`` fill the declared data
columns. The CSV contract writes a header and validates column names, order,
scalar types, and unique index values.

An analysis step may declare additional CSV or JSON outputs after its primary
output. When it does, implement ``additional_output_values`` and return a
mapping from each additional ``FileOutput`` object to the value that should be
written. The base class validates and serializes those values.

Connect parsed inputs to the analysis
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Implement ``analysis_kwargs(args)`` to construct the keyword arguments for
``analysis_cls``. File arguments are already parsed and validated through
their inherited file contracts. For example, a target-gene JSON input is
available as ``args.target_gene`` containing a ``TargetGene`` object; the
contributor should not open or deserialize it again.

The ``AnalysisStep`` base class then:

1. constructs the analysis;
2. supplies the configured analysis-worker count through ``n_processes``;
3. calls ``run``;
4. converts the site-keyed results to primary CSV rows; and
5. validates and writes every declared output.

There is no contributor-defined ``main`` function, input-loading hook,
metadata payload, or output-writing hook in the standard analysis-step flow.

Configuration and validation
----------------------------

For a built-in step, add new configuration fields to
``src/ASOkai/_pipeline/config.schema.yaml`` and document them in
``examples/config.example.yaml``. Reuse existing fields when they already
represent the required value.

The shared schema already defines the
``steps.<consumer>.inputs.<input>.parameters`` and ``path_override``
structure. Adding a configurable input does not require another schema entry;
its allowed parameter names and value types come from the ``FileInput`` and
the producer's ``ScalarParam`` declarations.

The YAML schema should express types, required fields, enumerated values,
ranges, and other structural constraints. Override
``validate_parameters(values)`` only for relationships between resolved
scalar parameters that the YAML schema cannot express clearly.

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

      class ExampleAnalysis(SiteSpecificAnalysis):
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
A plugin may nevertheless reuse ASOkai's contract renderer in its own Sphinx
documentation and supply its registered step, schema, and example
configuration there. This is optional: the runtime plugin contract requires
the ``asokai.steps`` entry point and, when the plugin owns configuration, the
``asokai.config_schemas`` entry point; it does not require Sphinx documentation.

Registration
------------

Built-in analysis steps live in
``src/ASOkai/_pipeline/steps/analysis`` and are added to ``_BUILTIN_STEPS`` in
``src/ASOkai/_pipeline/catalog.py``.

Add a built-in analysis class to the API page matching its scope:
``docs/source/api/modules/Analysis/site-specific.rst``,
``target-specific.rst``, or ``genome-wide.rst``. Add an ``autoclass`` entry
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
