.. _sec-idl-linter:

Linter
======

The **Yace**-file linter (``yace --lint <file>``), checks the given files for
integrity issues. This inclused issues from as invalid YAML-structure or
invalid YACE entities.

Below are examples of what you can expect to see when running it on a valid
**Yace**-file and on an invalid **Yace**-file.

Valid
-----

.. literalinclude:: 100_linter.cmd
   :language: yaml
   :lines: 1-

.. literalinclude:: 100_linter.out
   :language: yaml
   :lines: 1-

Invalid
-------

.. literalinclude:: 200_linter.uone.cmd
   :language: yaml
   :lines: 1-

.. literalinclude:: 200_linter.uone.out
   :language: yaml
   :lines: 1-

Implementation
--------------

.. automodule:: yace.idl.linter
   :inherited-members:
   :members:
   :undoc-members:
