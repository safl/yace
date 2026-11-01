.. _sec-ir-files:

Storage Format
==============

The IR is stored as YAML: ``meta``, describing the API, and ``entities``, its
declarations, in the order of the header. Each entity, and each type, has a
``key`` telling which kind it is, such as ``struct_decl`` or ``pointer``; the
classes are in :ref:`sec-ir-entities`, and listed by key in :ref:`sec-ir-list`.

Attributes at their default are left out. The IR of the example library is in
:ref:`sec-ir-cparser`.

The JSON Schema of the IR, for reading it without **yace**, is printed by::

  yace --schema
