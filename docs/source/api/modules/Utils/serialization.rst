Serialization
=============

``Serializable`` provides the dictionary representation used by ASOkai's
typed JSON file contracts. File reading, writing, and schema validation belong
to ``JsonFile``; domain classes inherit ``Serializable`` only to describe how
their values become JSON-compatible data.

Serialized fields are declared with class annotations. Constructors may accept
additional keyword attributes, but those undeclared values must be JSON scalar
values: strings, integers, floating-point numbers, booleans, or ``None``.

.. autoclass:: ASOkai.Utils.Serializable
   :members:
   :show-inheritance:
