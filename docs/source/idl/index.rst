.. _sec-idl:

======================
 Interface Definition
======================

In **Yace**, the C API and FFI are defined by a **Yace**-file. The content of a
**Yace**-file is described in the following sections. **Yace**-file can be
written manually, or with assistance from other tools, such as the
:ref:`sec-idl-generator`.

Regardless on how you produce the **Yace**-file, then a :ref:`sec-idl-linter`
is provided to check that the interface-definition is correct, and
:ref:`sec-idl-formater` to format the definition in a canonical fashion.

The descriptions inside the **Yace**-file consists of meta-data and then
descriptions of symbolic constants, data types, derived types, and function
types. These are referred to as :ref:`sec-idl-entities` and a
:ref:`sec-idl-list` for quick lookup is also available.

* :ref:`sec-idl-files`

  * :ref:`sec-idl-linter`
  * :ref:`sec-idl-formater`
  * :ref:`sec-idl-generator`

* :ref:`sec-idl-entities`
* :ref:`sec-idl-list`

.. toctree::
   :maxdepth: 2
   :hidden:

   files.rst
   linter.rst
   formater.rst
   generator.rst
   entities/index.rst
   list.rst
