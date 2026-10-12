Tasks
=====

Tasks group related steps into reusable pipeline operations. Their references
are generated from the built-in task registry. A task may expose public output
aliases, or leave ``outputs`` empty and let callers link to its named child
runs directly.

.. toctree::
   :hidden:
   :maxdepth: 1
   :glob:

   *

Core tasks
----------

.. asokai-runnable-list:: task core

Analysis tasks
--------------

.. asokai-runnable-list:: task analysis

Utility tasks
-------------

.. asokai-runnable-list:: task utils
