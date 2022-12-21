.. _sec-features:

Features
========

Tools related to **yace**, :autopxd2:`autopxd2 <>`, :ctypeslib2:`ctypeslib2
<>`, :rust-bindgen:`rust-bindgen <>` all parse the C headers for the library
they are producing language bindings / wrappers for.

**yace** differs from these projects as it generates the library C header as
well and instead of C headers use an interface model,  as the basis for
generating the C API and the language bindings / wrappers. The

.. _sec-features-codegen:

Code Generation
---------------

**yace** currently emits:

* C API

  * doxygen commented
  * pretty-printers for enums/structs/unions

With wrapper code for the following target languages:

* Python / ctypes [wip]
* Python / Cython [wip]
* Rust [wip]

.. _sec-features-model:

Interface Model
---------------

The interface-model **yace** uses to generate C APIs and FFI-bindings/wrappers
to the C API supports descriptions of the following C language constructs:

* define
* enum
* struct
* union
* plain datatypes
* function declaration [wip]

For details and reference see the :ref:`sec-model` section for a usage
introduction then follow the :ref:`sec-tutorial`.
