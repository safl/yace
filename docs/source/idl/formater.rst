.. _sec-idl-formater:

Formater
========

The ``yidl``-formater is invoked via the ``yace`` command-line. Below are
examples of what you can expect to see when running it on a valid ``yidl`` in a
before/after fashion.

Invoking it
-----------

.. literalinclude:: 300_formater.cmd
   :language: yaml
   :lines: 1-


Before
~~~~~~

.. literalinclude:: before.yaml
   :language: yaml
   :lines: 1-

After
~~~~~

.. literalinclude:: after.yaml
   :language: yaml
   :lines: 1-

.. _sec-idl-formater-implementation:

Implementation
--------------

.. automodule:: yace.idl.formater
   :inherited-members:
   :members:
   :undoc-members:
