.. _sec-idl:

======================
 Interface Definition
======================

In **Yace**, the C API and FFI are defined by a **Yace**-file. The content of a
**Yace**-file is described in the following sections. **Yace**-file can be
written manually, or with assistance from other tools, such as the generator.

Regardless on how you produce the **Yace**-file, then a :ref:`sec-idl-linter`
is provided to check that the interface-definition is correct, and
:ref:`sec-idl-formater` to format the definition in a canonical fashion.

* :ref:`sec-idl-files`

  * :ref:`sec-idl-linter`
  * :ref:`sec-idl-formater`
  * Generator (C Header to Yace-File)

* :ref:`sec-idl-entities`
* :ref:`sec-idl-list`

.. toctree::
   :maxdepth: 2
   :hidden:

   files.rst
   linter.rst
   formater.rst
   entities/index.rst
   list.rst
