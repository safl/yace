.. _sec-idl:

======================
 Interface Definition
======================

In **Yace**, one defines an abstract **FFI** as a subset of valid C.

Commonly then **FFIs** only enable calling functions. The challenge is then to
to ensure that the data the function operates on is mapped correctly from one
language to the other. This is often a delicate and highly error-prone process
leading to frustation due to unexpected behavior.

Issues arise alread in the representation of data types, onwards to a lack
in equivalent representation of data structures. **Yace** seeks to lower this
frustration by:

* Describing the IDL

  - How data types are mapped
  - How data structures are representated

And more importantly **Why**, by describing the portability / interoperability
of a given C API, and how to turn it into something less frustrating by making
it more robust and predictable.

As a reference, then the **Yace** IDL is by design primarily restricted by
the FFI capabilties of Rust and Python. These are selected as their serve to
extremes of statically compiled and safe usage, and dynamically loaded and
completely unsafe code for rapid prototyping and experimentation.

Here a description of things that are perfectly valid C but dis-allowed in
**Yace** are described, along with the internal representation and storage
**format.


* :ref:`sec-idl-files`

  * :ref:`sec-idl-generator`

* :ref:`sec-idl-entities`
* :ref:`sec-idl-list`

.. toctree::
   :maxdepth: 2
   :hidden:

   csubset.rst
   files.rst
   generator.rst
   entities/index.rst
   list.rst
