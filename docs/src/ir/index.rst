.. _sec-ir:

======================
 Interface Definition
======================

In **yace**, the FFI boundary of a C API is described by a C header in a subset
of C99. The subset is what can be described equivalently in C, C++, Python,
Rust and Zig: the types, the records and the functions that cross the boundary,
and nothing that only makes sense in one of them.

The header is parsed into the IR, the intermediate representation, which the
targets generate code from. Each target generates code that is idiomatic for its
language, the C target included: the C header it generates is not the one you
wrote, but the C API derived from it, and may use what C allows and the subset
does not.

What is the same across all of them is the ABI: the layout of every record and
the signature of every function. The IR records the layout as the compiler laid
it out, and every target checks what it generates against it.

* :ref:`sec-ir-background`, the API, the ABI, and what yace does about each
* :ref:`sec-ir-csubset`, the subset, and why
* :ref:`sec-ir-rules`, the rules, as **yace** reports them
* :ref:`sec-ir-cparser`, parsing a header
* :ref:`sec-ir-files`, the IR as stored
* :ref:`sec-ir-entities`, the IR as Python classes

.. toctree::
   :maxdepth: 2
   :hidden:

   background.rst
   csubset.rst
   rules.rst
   cparser.rst
   files.rst
   entities/index.rst
   list.rst
