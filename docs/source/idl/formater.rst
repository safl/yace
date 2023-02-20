.. _sec-idl-formater:

Formater
========

The **Yace**-file formater, ``yace --format <filepath>``. Below are examples of
what you can expect to see when running it on a valid **Yace**-file in a
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
