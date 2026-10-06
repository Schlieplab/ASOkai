Internal steps
==============

Internal steps are registered pipeline steps that are omitted from the default
``asokai list steps`` output. Set ``listed = False`` on a step class when it
supports another pipeline component but is not intended for the main step
catalog. An internal step still has a ``StepSpec``, can be selected by name,
and appears in ``asokai list -v steps``. Use ``asokai describe step <name>``
to inspect its inputs and outputs, or add ``-v`` for more detail.

Built-in internal steps
-----------------------

.. asokai-step-list:: internal
   :descriptions:
