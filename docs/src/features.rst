.. SPDX-FileCopyrightText: Simon A. F. Lund <os@safl.dk>
..
.. SPDX-License-Identifier: GPL-2.0-only

.. _sec-features:

Features
========

**yace** is yet another code emitter. Related code emitters, such as
:autopxd2:`autopxd2 <>`, :ctypeslib2:`ctypeslib2 <>` and
:rust-bindgen:`rust-bindgen <>`, generate bindings from the C header of the
library that they wrap.

**yace** in turn does not use the library C header, instead it uses an
:ref:`sec-ir`, and rather than consuming the C header, then it
**produces** it!

This is useful for systems libraries where header definitions are
representations of hardware communication protocols, and C-structs provide
memory accessors and decode payloads to/from devices.

C is well suited to systems programming, and other languages are better suited
to other tasks. A program in another language accesses a C library through a
foreign-function interface (FFI).

**yace** generates the bindings for such an interface. Other code emitters do
so as well; what **yace** adds is:

Documentation
  The :ref:`sec-ir` requires documentation of all symbols, so the generated
  bindings are documented too: in Doxygen format for C code, in PyDoc for
  Python, and so on.

Syntactic sugar
  The :ref:`sec-ir` is close to C, but has higher-level constructs, from which
  **yace** emits code that is more Pythonic, idiomatic Go and Rust, and modern
  C++. The generated bindings thus have a thin layer of syntactic sugar over
  the raw FFI of each language.

Pretty-printers
  The :ref:`sec-ir` describes the data structures, so **yace** emits functions
  that pretty-print the enums, structs and unions, in YAML and JSON.

Fields of bits
  C bit-fields do not cross an FFI boundary, so a field of bits is an integer
  whose parts are named by masks. The :ref:`sec-ir` links each mask to its
  field, from the doc comments, so the pretty-printers print the parts by
  name, and every target reads and writes them by name.

For an introduction to using **yace**, see :ref:`sec-usage`. For details and
reference, see :ref:`sec-ir`, and for the supported targets, see
:ref:`sec-targets`.
