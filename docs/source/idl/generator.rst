.. _sec-idl-generator:

Generator
=========

The **Yace**-file generator, invoked by: ``yace --c-to-yace <filepath>``. Below
are examples of what you can expect to see when running it on C a header. 

.. note:: The generator is implemented using Python bindings to libclang.
   Thus, libclang must be loadable on the system.

Invoking it
-----------

.. literalinclude:: 400_generator.cmd
   :language: bash

C Header
~~~~~~~~

.. literalinclude:: example.h
   :language: c
   :caption:

Yace File
~~~~~~~~~

.. literalinclude:: output/example_parsed.yaml
   :language: yaml
   :caption:

.. _sec-idl-generator-implementation:

Implementation
--------------

.. automodule:: yace.idl.generator
   :inherited-members:
   :members:
   :undoc-members:
