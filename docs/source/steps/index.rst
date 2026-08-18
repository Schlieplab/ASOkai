Steps
=====

Steps are independently runnable pipeline units with declared configuration,
inputs, outputs, and dependencies. Each reference page documents one step's
runtime contract.

Core steps
----------

Core steps establish the shared data used by the rest of the pipeline:

.. asokai-step-list:: core
   :descriptions:

Analysis steps
--------------

Analysis steps calculate properties of pipeline data and write typed result
tables. Built-in analysis steps are listed below.

.. asokai-step-list:: analysis
   :descriptions:
