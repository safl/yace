.. _sec-features:

Features
========

**yace** is yet another code emitter, it is natural to ask, why is another
needed? And the answer is that related code-emitters such as
:autopxd2:`autopxd2 <>`, :ctypeslib2:`ctypeslib2 <>`,
:rust-bindgen:`rust-bindgen <>`, generate bindings based on the C header that
they are wrapping / producing language bindings for.

**yace** in turn does not use the library C header, instead it uses an
:ref:`sec-model`, and rather than consuming the C header, then it
**produces** it!

This is useful for systems libraries where header definitions are
representations of hardware communication protocols, and C-structs provide
memory accessors and decode payloads to/from devices.

Adding to this, C is an excellent language for systems programming; however, C
could be better for some things... yet there are plenty of great languages to
choose from and access to the system the C library provided can be done via
foreign-function-interfaces (FFI).

This is where **yace** steps in and provides bindings those bindings. As
mentioned before, then other code emitters can do this as well, however,
**yace** introduces some niceties:

* **Documentation**; the :ref:`sec-model` requires documentation of all symbols,
  this means that generated wrappers/bindings also get documentation, e.g. in
  DoxyGen format for C code, in PyDoc for Python etc.

* **Sugar**; the :ref:`sec-model` is very close to C code, yet, it has some
  higher-level constructs which enables it to exploit the semantics emit code
  which is slightly more **Pythonic**, **idiomatic Go / Rust**, and **Modern
  C++**.
  That is, the generated bindings can have small layers of **syntactic sugar**,
  sanding down the rough edges of the raw FFI interface of the language.

* **Pretty-printers**; since **yace** knows the data-structures via the
  :ref:`sec-model`, then the emitter can produce helper-functions
  pretty-printing those enums, structs, and unions in **YAML**, **JSON**.

For a quick introduction to using **yace** then jump to the :ref:`sec-usage`
section. For details and reference see the :ref:`sec-model`.

.. _sec-features-codegen:

Code Generation
---------------

**yace** currently emits:

* C API

  * doxygen commented
  * pretty-printers for enums/structs/unions

With wrapper code for the following target languages:

* C++ [wip]
* Go [wip]
* Python / Cython [wip]
* Python / ctypes [wip]
* Rust [wip]
