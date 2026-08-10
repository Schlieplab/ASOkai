Adding an analysis step
=======================

An analysis contribution has two parts:

1. an analysis class containing the scientific calculation; and
2. an :class:`~ASOkai.Plugins.AnalysisStep` describing how that calculation
   participates in the pipeline.

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
sites and handles multiprocessing, so contributors normally do not override
it.

Declare the pipeline contract
-----------------------------

An analysis step inherits from :class:`~ASOkai.Plugins.AnalysisStep` and
declares ``name``, ``description``, ``analysis_cls``, and ``spec``. Import
contributor-facing pipeline types from :mod:`ASOkai.Plugins`.

The :class:`~ASOkai.Plugins.StepSpec` contains three kinds of declarations:

``ScalarParam``
   A scalar command-line argument, optionally populated from a dotted
   configuration path.

``FileInput``
   A file produced by another step. Its ``source`` is that step's
   ``FileOutput`` declaration. This connection supplies the dependency and
   file type automatically. If ``override`` is configured, a user may provide
   a pre-existing file with the same contract.

``FileOutput``
   A produced file, its type, and its destination below the configured data
   directory. ``JsonFile`` validates serializable object structures;
   ``CsvFile`` declares ordered index and data columns with scalar types.

Declare every ``FileOutput`` once as a class attribute and reuse that object
in ``StepSpec.outputs``. Referencing that class attribute from a later
``FileInput`` connects the steps without a separate dependency list.

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

The :class:`~ASOkai.Plugins.AnalysisStep` base class then:

1. constructs the analysis;
2. supplies the configured process count;
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

The YAML schema should express types, required fields, enumerated values,
ranges, and other structural constraints. Override
``validate_parameters(values)`` only for relationships between resolved
scalar parameters that the YAML schema cannot express clearly.

Use ``StepSpec.compatible_with`` only for real biological applicability
restrictions, such as a mechanism or modality required by the analysis. Omit
it when the analysis is generally applicable.

Registration
------------

Built-in analysis steps live in
``src/ASOkai/_pipeline/steps/analysis`` and are added to ``_BUILTIN_STEPS`` in
``src/ASOkai/Plugins/_registry.py``.

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

The pipeline-reference pages are generated from step declarations. Keep the
step description, parameter documentation, file contracts, and analysis class
docstrings clear because those declarations are also the documentation source.
