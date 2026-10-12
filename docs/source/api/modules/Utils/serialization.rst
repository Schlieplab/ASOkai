Serialization
=============

``Serializable`` provides the dictionary representation used by ASOkai's
typed JSON file contracts. File reading, writing, and schema validation belong
to ``JsonFile``; domain classes inherit ``Serializable`` only to describe how
their values become JSON-compatible data.

Typed ``JsonFile`` documents have a ``root`` value and an ``objects`` table.
Objects used once are written inline. When the same ``Serializable`` instance
is used more than once, it is stored in the table and each use contains a
``$ref`` pointer to that entry. Loading restores those references to the same
Python instance. A single shared object of a class uses the class name as its
table key; several shared objects of that class receive numbered keys.
``JsonFile`` also reads earlier inline files and files that put every object
in the table.

Serialized fields are declared with class annotations. Constructors may accept
additional keyword attributes. Those undeclared values are plain JSON data:
string-keyed mappings and lists containing strings, numbers, booleans, or
``None``.

.. autoclass:: ASOkai.Utils.Serializable
   :members:
   :show-inheritance:
