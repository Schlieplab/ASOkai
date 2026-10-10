Analyses
========

An analysis can be one step or a task that prepares inputs through several
steps. The step that writes a result table declares its CSV output. A task may
expose that output under a public name, or callers may link directly to the
child run's output.

Built-in analysis steps and tasks are listed together below.
Use ``asokai list analyses`` to see the same category in the installed CLI,
including analysis plugins. Each entry is labeled as a step or task.

Inspect either kind with ``asokai describe analysis NAME``. For example,
``asokai describe analysis compute-intrinsic-features`` describes a step, and
``asokai describe analysis find-repeated-sites`` describes a task. Add ``-v``
for configuration keys, file details, and dependency information.

.. asokai-analysis-list::
