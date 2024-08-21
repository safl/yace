.. _sec-idl:

======================
 Interface Definition
======================

In **Yace**, the C API and FFI are defined by a **Yace**-file. The content of a
**Yace**-file is described in the following sections. **Yace**-file can be
written manually, or with assistance from other tools, such as the
:ref:`sec-idl-generator`.

The storage format for the **Yace** Interface Defitinion is in **YAML**. Thus,
no extra tooling for linting and visualizing it, just use regular formaters and
visualization tools such as **jless**. The content is validated when loaded.

The descriptions inside the **Yace**-file consists of meta-data and then
descriptions of symbolic constants, data types, derived types, and function
types. These are referred to as :ref:`sec-idl-entities` and a
:ref:`sec-idl-list` for quick lookup is also available.

* :ref:`sec-idl-files`

  * :ref:`sec-idl-generator`

* :ref:`sec-idl-entities`
* :ref:`sec-idl-list`

.. toctree::
   :maxdepth: 2
   :hidden:

   files.rst
   generator.rst
   entities/index.rst
   list.rst
