Serialization
=============

``Serializable`` provides the dictionary representation used by ASOkai's
typed JSON file contracts. File reading, writing, and schema validation belong
to ``JsonFile``; domain classes inherit ``Serializable`` only to describe how
their values become JSON-compatible data.

.. autoclass:: ASOkai.Utils.Serializable
   :members:
   :show-inheritance:
