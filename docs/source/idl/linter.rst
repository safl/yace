Linter
======

The ``yidl``-linter is called via the ``yace`` command-line. Below are examples
of what you can expect to see when running it on a valid ``yidl`` and on an
invalid ``yidl``.

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
