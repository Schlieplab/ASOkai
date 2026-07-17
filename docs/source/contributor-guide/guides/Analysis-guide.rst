Analysis Development Guide
==========================

This guide describes how to add a new analysis to :mod:`ASOkai`.

Adding an analysis usually involves the following steps:

1. Implement the analysis class.
2. Implement the corresponding analysis step class.
3. Add the analysis step to the registry.
4. Add the analysis step to a task or workflow, where applicable.
5. Test the implementation.
6. Write documentation.
7. Submit a pull request.

Before starting, read the :doc:`Analysis API documentation <../../api/modules/Analysis>`.
It explains the available analysis scopes and how to choose between
:class:`~ASOkai.Analysis.SiteSpecificAnalysis`,
:class:`~ASOkai.Analysis.TargetSpecificAnalysis`, and
:class:`~ASOkai.Analysis.GenomeWideAnalysis`.

For a working reference, see :class:`~ASOkai.Analysis.IntrinsicFeaturesAnalysis`, which provides an example of a site-specific analysis implementation.

1. Implement the analysis class
--------------------------------

Create a new analysis module in
``src/ASOkai/Analysis/_<analysis_name>.py``. For example, an analysis named
``MyAnalysis`` can be implemented in ``src/ASOkai/Analysis/_my_analysis.py``.

The analysis class must inherit from the base class that matches the context
required by the analysis.

Each analysis class must implement
:meth:`~ASOkai.Analysis.Analysis.analyze`. This method receives one site and
returns a ``dict[str, Scalar]`` containing the calculated values for that
site.

In most cases, the class should also implement ``__init__`` to accept
analysis-specific arguments or configuration. Call ``super().__init__(...)``
to initialize the inherited analysis state, including ``sites`` and shared
configuration.

:meth:`~ASOkai.Analysis.Analysis.run` processes all configured sites by
calling ``analyze``. Do not override ``run`` in an analysis class.

Example:

.. code-block:: python

   from ..Types import Scalar
   from ._base import SiteSpecificAnalysis


   class MyAnalysis(SiteSpecificAnalysis):
       """Compute a custom value for each site."""

       def __init__(self, sites: list, threshold: float = 0.0, **kwargs):
           super().__init__(sites, **kwargs)
           self.threshold = threshold

       def analyze(self, site) -> dict[str, Scalar]:
           return {"my_feature": 0.0}

After implementing the class, export it from
``src/ASOkai/Analysis/__init__.py`` so it can be imported through the public
``ASOkai.Analysis`` interface.

For example:

.. code-block:: python

   from ._my_analysis import MyAnalysis

2. Implement the analysis step class
------------------------------------

Create a new analysis step module at
``src/ASOkai/_pipeline/steps/<analysis_name>.py``. For example, the analysis
``my-analysis`` should have its step implementation in
``src/ASOkai/_pipeline/steps/my_analysis.py``.

The step class must inherit from :class:`~ASOkai._pipeline.base.AnalysisStep`.

Before implementing an analysis step, read the
:doc:`Pipeline Components documentation <./Pipeline-components>`.
It describes the role of :class:`~ASOkai._pipeline.base.AnalysisStep` and its
available customization methods.

The analysis step connects the analysis class from step 1 to the ASOkai
pipeline. It defines the command-line interface, loads the required inputs,
constructs the analysis class, and writes the analysis output.

The step class should define the following class attributes:

- ``name``: the name used for this analysis in the command-line interface.
- ``description``: a short description of what the analysis does.
- ``analysis_cls``: the analysis class implemented in step 1.
- ``cli_module``: the Python module containing the step, written as
  ``"ASOkai._pipeline.steps.<analysis_name>"``.
- ``dependencies``: names of pipeline steps that must run before this step.
- ``spec``: the :class:`~ASOkai._cwl.spec.StepSpec` that defines the step
  parameters, inputs, outputs, and output paths.

.. todo::

   ``StepSpec`` and its parameter, input, output, and path-template interfaces
   will be documented on a separate page.

   Until then, see ``src/ASOkai/_cwl/spec.py`` and existing step classes for
   implementation examples.

The following methods should be implemented for an analysis step:

- ``load_analysis_inputs(args)``: load the objects required by the analysis.
- ``analysis_kwargs(args, inputs)``: return the keyword arguments used to
  construct ``analysis_cls``.
- ``analysis_metadata(args, inputs)``: return metadata to write alongside the
  analysis results.

Other inherited methods, such as ``output_arg`` and
``write_analysis_output``, can be overridden when the default behavior is not
sufficient. In most analysis steps, however, only the three methods above need
to be implemented.

The default :meth:`~ASOkai._pipeline.base.AnalysisStep.run_from_args` method
calls these methods, constructs ``analysis_cls``, and runs the analysis. The
output payload is normally a dictionary containing the metadata returned by
``analysis_metadata`` and the results returned by
:meth:`~ASOkai.Analysis.Analysis.run`. ``run`` calls the ``analyze`` method
from step 1 once for each configured site.

Example
~~~~~~~

The following example shows the main structure of a site-specific analysis
step. Adapt the parameters, inputs, output path, dependencies, and metadata to
the requirements of the new analysis.

.. code-block:: python
   
    class MyAnalysisStep(AnalysisStep):
        name = "my-analysis"
        description = "Compute a custom value for each ASO target site."
        analysis_cls = MyAnalysis
        cli_module = "ASOkai._pipeline.steps.my_analysis"
        dependencies = ["create-target-gene"]

        spec = StepSpec(
            requirements={
                "WorkReuse": {"enableReuse": True},
            },
            params=[
                ScalarParam(
                    "assembly",
                    str,
                    config="genome.assembly_id",
                    doc="Assembly ID, for example GRCh38.",
                ),
                ScalarParam(
                    "target_id",
                    str | None,
                    config="target.target_id",
                    doc="Ensembl gene ID. Takes priority over target_name.",
                ),
                ScalarParam(
                    "target_name",
                    str | None,
                    config="target.target_name",
                    doc="Gene name used when target_id is not provided.",
                ),
                ScalarParam(
                    "k",
                    int,
                    config="target.k",
                    doc="ASO length.",
                ),
                ScalarParam(
                    "region",
                    TargetRegion,
                    config="target.region",
                    doc="Target region type.",
                ),
            ],
            inputs=[
                InputParam(
                    "target_gene",
                    override="target.target_gene_path",
                    doc="Serialized target gene object from create-target-gene.",
                ),
            ],
            outputs=[
                OutputParam(
                    "my_analysis",
                    temp_filename="my_analysis.json",
                    destination=OutputPathTemplate(
                        "{assembly}/targets/{target}/analysis/my_analysis/"
                        "{target}_k{k}_{region}_my_analysis.json",
                        fields={
                            "target": TemplateField.first_of(
                                "target_id",
                                "target_name",
                            ),
                        },
                    ),
                    doc="Custom analysis results per ASO target site.",
                ),
            ],
        )

        def load_analysis_inputs(self, args) -> dict:
            from ASOkai.Targets import TargetGene

            return {
                "target_gene": TargetGene.from_file(str(args.target_gene)),
            }

        def analysis_kwargs(self, args, inputs: dict) -> dict:
            return {
                "sites": inputs["target_gene"].sites,
            }

        def analysis_metadata(self, args, inputs: dict) -> dict:
            return {
                "analysis": self.name,
                "assembly": args.assembly,
                "target_id": args.target_id,
                "target_name": args.target_name,
                "k": args.k,
                "region": args.region,
            }

3. Add the analysis step to the registry
----------------------------------------

Add the new analysis step to ``src/ASOkai/_pipeline/registry.py``. Registering
the step makes it available to the ASOkai command-line interface and allows
the pipeline to generate the configuration required to run it.

First, import the new step class:

.. code-block:: python

   from ASOkai._pipeline.steps.my_analysis import MyAnalysisStep

Then add an instance of the step to ``_BUILTIN_STEPS``:

.. code-block:: python

   _BUILTIN_STEPS: list[Step] = [
       DownloadGenomeStep(),
       CreateTargetGeneStep(),
       IntrinsicFeaturesStep(),
       MyAnalysisStep(),
   ]

4. Add the analysis step to a task or workflow (optional)
---------------------------------------------------------

If the new analysis is part of a larger task or workflow, add the analysis
step to the relevant task or workflow definition.

This is not required for analyses that are intended to run independently from
the command-line interface.

.. todo::

   Documentation for creating and modifying tasks and workflows will be added
   in a later update. This part will be updated with real instructions when the documentation for tasks and workflows are available.
   For now, contact Arash :)

5. Test the implementation
--------------------------

Reinstall ASOkai in the active development environment so that the local implementation is used:

.. code-block:: bash

   python -m pip install -e .

First, test the new analysis step manually. Confirm that it loads its inputs,
constructs the associated analysis, and writes the expected output.

Next, add unit tests for the new step. Create a test file under
``tests/unit/`` named:

.. code-block:: text

   test_<analysis_step_name>_step.py

For example, tests for a step named ``my-analysis`` should be placed in:

.. code-block:: text

   tests/unit/test_my_analysis_step.py

The unit tests should cover the expected behavior of the analysis step,
including input loading, analysis arguments, metadata, output paths, and the
produced result where applicable. Take a look at ``tests/unit/test_intrinsic_features_step.py`` file
to get an idea on what unit tests are needed.


If the analysis step was added to a task or workflow, update or extend the
corresponding task or workflow unit tests as well.

Finally, update the CLI tests so that the new step is available and behaves as
expected through the command-line interface. See the intrinsic-features tests
in ``tests/test_cli_main.py`` as a working example.

Run the relevant tests during development, then run the complete test suite
before submitting the pull request:

.. code-block:: bash

   pytest tests/unit/test_<analysis_step_name>_step.py
   pytest

6. Write documentation
----------------------

Document the analysis class implemented in step 1. The class itself and its
overridden methods should include clear docstrings.

Sphinx uses ``autodoc`` and ``autosummary`` to generate the API reference from
these docstrings. Write docstrings in reStructuredText-compatible format so
that lists, code identifiers, links, and other formatting are rendered
correctly.

For reStructuredText syntax and formatting options, see the
`reStructuredText Primer <https://www.sphinx-doc.org/en/master/usage/restructuredtext/basics.html>`_.

After writing or updating docstrings, build the documentation locally and
review the generated API page:

.. code-block:: bash

   sphinx-build -M html docs/source docs/build

Open ``docs/build/html/index.html`` in a browser and check that the new class,
its constructor, and its overridden methods are documented clearly.

.. todo::

   A separate guide describing the ASOkai documentation structure and
   documentation-writing conventions will be added later.

7. Submit a pull request
-------------------------

Once all previous steps are done, create a pull request and inform Arash :).