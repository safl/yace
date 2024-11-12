.. _sec-idl-cparser:

C Parser
========

The **Yace**-file generator, invoked by: ``yace <file.c>``. Below are examples
of what you can expect to see when running it on C a header.

.. note:: The C Parser is implemented using Python bindings to libclang.
   Thus, libclang must be loadable on the system.

Invoking it
-----------

.. literalinclude:: 400_cparser.cmd
   :language: bash

C Header
~~~~~~~~

.. literalinclude:: ../../../models/example.h
   :language: c
   :caption:

Yace File
~~~~~~~~~

.. literalinclude:: ../../../models/example.yaml
   :language: yaml
   :caption:

.. _sec-idl-cparser-implementation:

Implementation
--------------

.. automodule:: yace.idl.cparser
   :inherited-members:
   :members:
   :undoc-members:
