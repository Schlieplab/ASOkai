Steps
=====

Steps are independently runnable pipeline units with declared configuration,
inputs, outputs, and dependencies. Each reference page documents one step's
runtime contract.

Use ``asokai list -v steps`` to include internal steps.
``asokai describe step <name>`` shows their details when named explicitly;
add ``-v`` for configuration keys, file details, and dependency trees.

Core steps
----------

Core steps establish the shared data used by the rest of the pipeline:

.. asokai-step-list:: core
   :descriptions:

Analysis steps
--------------

Analysis steps calculate properties of pipeline data and write typed result
tables. Built-in analysis steps are listed below. The :doc:`Analyses index
<../analyses/index>` also includes tasks that compose an analysis from multiple
steps.

.. asokai-step-list:: analysis
   :descriptions:

Utility steps
-------------

Utility steps perform reusable operations on supplied inputs. Run selections
or tasks can connect them to specific ASOkai data sources.

.. asokai-step-list:: utils
   :descriptions:
