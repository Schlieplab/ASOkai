Pipeline Components
===================

The :mod:`ASOkai._pipeline.base` module defines the common interfaces and base
classes used to construct ASOkai pipeline components.

Pipeline structure
------------------

ASOkai organizes pipeline functionality into steps, tasks, and workflows.

A :class:`Step` represents one atomic pipeline operation. Steps can be grouped
into :class:`Task` and :class:`Workflow` collections.

:class:`Runnable` defines the common interface shared by steps, tasks, and
workflows. Each runnable provides a name, description, declared output paths,
output-existence checks, and cleanup behavior.

Step types
-----------

:class:`Step` is the base class for an atomic pipeline operation. Each step
defines its parameters, inputs, outputs, and configuration mapping through its
``spec``.

.. todo::
    The ``StepSpec`` interface defining step inputs, outputs,
    parameters, and configuration will be documented on a separate page.

    Until then, see ``src/ASOkai/_cwl/spec.py`` for its implementation.

ASOkai provides two main step categories:

- :class:`CoreStep`: a pipeline step that is used to define fundamental processes of :mod:`ASOkai`.
- :class:`AnalysisStep`: a step that executes an
  :class:`~ASOkai.Analysis.Analysis` implementation and writes its results as
  JSON.

Analysis steps
--------------

An :class:`AnalysisStep` connects an analysis class to the pipeline interface.
It loads the required inputs, constructs the configured analysis class, runs
the analysis, and writes the resulting JSON output.

Each analysis step has an ``analysis_cls``, which identifies the associated
analysis class. It may override the following methods when required:

- ``load_analysis_inputs(args)``: load objects required by the analysis.
- ``analysis_kwargs(args, inputs)``: build keyword arguments used to construct
  ``analysis_cls``.
- ``analysis_metadata(args, inputs)``: define metadata written alongside the
  analysis results.
- ``output_arg(args)``: select an output argument when the step has multiple
  outputs.
- ``write_analysis_output(args, payload)``: customize result-output writing.

The default :meth:`AnalysisStep.run_from_args` implementation loads inputs,
creates the analysis, calls :meth:`~ASOkai.Analysis.Analysis.run`, and writes
a JSON payload containing metadata and results.

.. important::

   New analysis-step classes should normally implement only the input-loading
   and argument-construction methods required by their analysis. Do not
   override :meth:`AnalysisStep.run_from_args` unless the default execution
   and JSON-output behavior is insufficient.

Tasks and workflows
-------------------

A :class:`Task` is a collection of :class:`Step` objects.

A :class:`Workflow` is a collection of :class:`Runnable` components. A
workflow may contain steps, tasks, or other workflows. Its members are
recursively flattened into steps when pipeline jobs are generated.

API reference
-------------

.. automodule:: ASOkai._pipeline.base
   :members:
   :undoc-members:
   :show-inheritance: