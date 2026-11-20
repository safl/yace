.. SPDX-FileCopyrightText: Simon A. F. Lund <os@safl.dk>
..
.. SPDX-License-Identifier: GPL-2.0-only

.. _sec-targets-cython:

cython
======

The Cython target, ``cython``, generates the idiomatic API of the Python target
as a module compiled with Cython. It also generates a ``.pxd`` that declares
the C API for Cython code. The files are written to ``<output>/cython``:

``<prefix>.pyx``
  The module. Where the prefix is the name of a module of the standard library,
  such as ``zlib``, the file is ``<prefix>_.pyx``, as in the Python target.

``<prefix>.pyi``
  The stub of the module: the types of its functions, classes and constants,
  which a type checker cannot read from a compiled module. The stub is
  formatted by black and imports ``disjoint_base`` from ``typing_extensions``.

``<prefix>.pxd``, ``lib<prefix>.h``
  The C API for Cython, see :ref:`sec-targets-cython-pxd`, and the header it
  declares, as the C target emits it.

``<prefix>_check.py``
  The check program, not part of the API. It prints a zeroed instance of every
  record as YAML or JSON.

``<prefix>_check.pyx``
  The check of the ``.pxd``, not part of the API. It assigns each name that the
  ``.pxd`` declares to a variable of the type the ``.pxd`` gives it.

The check needs Cython in the Python environment of **yace**, and a C compiler.
It runs these steps:

1. Translate ``<prefix>_check.pyx`` and compile the C with the header. A
   declaration of the ``.pxd`` that disagrees with the header fails to compile.
   The type of a bit-field is not checked, as a bit-field has no address.
2. Translate the module and compile it, without linking the library. A wrong
   conversion of a pointer or an integer is an error.
3. Run the check program. It imports the module, with the functions of the
   library resolved only when called, and calls none of them. **yace** parses
   the output as YAML and as JSON.

The check does not check the stub. The tests of **yace** compare the stub with
the module using mypy's stubtest.

The module
----------

The module has the same API as the idiomatic layer of the Python target, see
:ref:`sec-targets-python`: the same names, parameters, results and errors. Code
written against one runs against the other. The module has no raw layer;
Cython code calls C through the ``.pxd``. The two modules differ in these
ways:

Records
  A struct or union with fields is an extension type that holds the C struct.
  A record inside another record, as a field or an element of an array field,
  is a view of the C memory and keeps the outer record alive. A pointer to a
  record that the library returns is a view too, and one to a ``const`` record
  a copy, unless the record ends in a flexible array. An array field is a
  :py:class:`memoryview` of the C memory. An array of ``char`` is
  :py:class:`bytes`, up to the first NUL. A pointer field is an
  :py:class:`int` address, or ``None`` for NULL. A string set to a field is
  kept alive by the record that holds the C memory, and by any record it is
  copied to. A record or array field of a packed record is read as a copy, as
  its address may be unaligned. The pretty-printers, ``str()`` and ``repr()``
  are those of the Python target.

Arrays
  An array argument is any object with the buffer protocol whose elements match
  the size and kind of the C type: an :py:class:`array.array`, a
  :py:class:`memoryview`, :py:class:`bytes` for ``uint8_t``, or a NumPy array.
  C reads and writes the buffer without a copy. Any other sequence, such as a
  list, is copied into an :py:class:`array.array`, and an ``[in,out]`` one is
  copied back. A ``void *`` ``@arrparam`` takes any buffer. An ``[out]`` array
  is returned as an :py:class:`array.array` of the given capacity, truncated
  to the count written; a ``void *`` one as a :py:class:`bytearray`. An array
  of records or of strings is copied. An ``[out]`` array of pointers to
  records is a list of views of the records, which C is given back as the
  same records, or of copies where the records are ``const``, as the Python
  target returns them.

Handles
  A handle is an extension type. Its destructor is called from
  ``__dealloc__`` when the last reference goes. A handle is made by the API
  only, not by calling its class.

Pointers
  A pointer to a type the module has no class for, such as ``void *`` or
  ``FILE *``, is an :py:class:`int` address, or ``None`` for NULL. A callback
  without ``@lifetime`` is the address of a C function.

Enumerations
  Each enum is made by calling :py:class:`enum.IntEnum`, as a member may have a
  name Cython reserves, such as ``DEF``.

Names
  A name that the ``.pxd`` also declares, a Python builtin such as ``len``, or
  a name Cython reserves such as ``include``, is defined under another name
  and bound to its own name in the module's globals. A class named as
  something the ``.pxd`` declares gets a trailing ``_`` and is bound to its own
  name too. A field named as a Python keyword or a name Cython reserves gets a
  trailing ``_``: ``class_``, or ``class__`` where a field ``class_`` exists.
  Where the module defines a Python name the stub uses, such as ``list`` for
  ``foo_list()``, the stub imports that name as ``_list``.

The module is built as a Cython extension, linked against the library. With
meson-python, the ``pyproject.toml`` of the package names the build backend:

.. code-block:: toml

   [build-system]
   build-backend = "mesonpy"
   requires = ["meson-python", "Cython"]

   [project]
   name = "foo"
   version = "1.0.0"

The ``meson.build`` beside it builds the module, finds the library through its
pkg-config file, and installs the stub, the ``.pxd`` and the header beside the
module, so type checkers find the types and Cython code can cimport the C API:

.. code-block:: meson

   project('foo', 'c', 'cython')

   py = import('python').find_installation(pure: false)
   foo = dependency('foo')

   py.extension_module(
     'foo',
     'output/cython/foo.pyx',
     dependencies: foo,
     include_directories: 'output/cython',
     install: true,
   )
   py.install_sources(
     'output/cython/foo.pyi',
     'output/cython/foo.pxd',
     'output/cython/libfoo.h',
   )

``pip install .`` builds and installs the package, and ``python -m build``
makes its sdist and wheel.

The module is not built for the limited API of Python, which would let one
build run on every CPython from 3.12. Under the limited API of 3.12, every
change of a reference count and every conversion of an integer is a function
call into Python. Built for it, ``cython-idiomatic`` in the table under
:ref:`sec-targets-cython-performance` takes 84.0 ns per point for calls and
111.8 ns with a callback.

.. _sec-targets-cython-pxd:

The C API for Cython
--------------------

``<prefix>.pxd`` declares the C API, its records, enums, defines and functions,
in a ``cdef extern`` block of ``lib<prefix>.h``. The block is ``nogil``, so
Cython code can call the functions without the GIL:

.. code-block:: cython

   cimport foo as lib

   def count(int times):
       cdef lib.foo_handle *handle = NULL
       if lib.foo_open(b"loop", &handle):
           raise OSError("foo_open() failed")
       ...

The ``.pxd`` has the name of the module and sits beside it, so ``cimport foo``
finds the declarations and ``import foo`` the module. Cimporting it under
another name, such as ``lib``, also works for a prefix that Cython reserves,
such as ``api``.

The names are those of the C API, except for three kinds: names Cython
reserves, such as ``include``; Python builtins, such as ``len``, which would
hide the builtin from the module; and tags of records and enums that share a
name with a function, define, enum member or typedef, which C keeps apart and
Cython does not. These are declared with a trailing ``_`` and their C name:
``int include_ "include"(int cdef_)``. A flexible array member is left out, as
Cython has none, and a comment says so.

An extension that uses the ``.pxd`` is built with ``<output>/cython`` on the
include path of both Cython and the C compiler, and linked against the
library. meson does not pass ``include_directories`` to Cython, so the
``meson.build`` gives Cython the path too:

.. code-block:: meson

   py.extension_module(
     'loop',
     'loop.pyx',
     dependencies: foo,
     include_directories: 'output/cython',
     cython_args: ['-I', meson.current_source_dir() / 'output/cython'],
     install: true,
   )

``examples/libfoo/checks/cython`` builds ``check.pyx``, which calls libfoo
this way.

.. _sec-targets-cython-performance:

Performance
-----------

:ref:`sec-bench` measures calls of libfoo from every target against C. On a
Ryzen 7 7840U under WSL2, summing the 8 points of libfoo 200000 times, best of
5 runs, in nanoseconds per point:

.. list-table::
   :header-rows: 1

   * - target
     - calls
     - callback
   * - ``c``
     - 1.9
     - 2.1
   * - ``python-raw``
     - 384.9
     - 204.2
   * - ``python-idiomatic``
     - 580.3
     - 412.4
   * - ``cython-raw``
     - 1.3
     - 1.5
   * - ``cython-idiomatic``
     - 56.9
     - 84.5

``cython-idiomatic`` runs the Python loops of ``python-idiomatic`` against the
module of this target. ``cython-raw`` is a loop in Cython that calls C through
the ``.pxd``.

Example
-------

.. literalinclude:: 200_yace.cmd
   :language: bash
   :lines: 1-

.. literalinclude:: 300_output.out
   :language: text
   :lines: 1-

``examples/libfoo/checks/python/idiomatic.py``, the check of the idiomatic
layer of the Python target, also runs against the module.

Bindings
~~~~~~~~

.. literalinclude:: ../../../../output/cython/foo.pyx
   :language: cython
   :caption:
   :lines: 1-

.. literalinclude:: ../../../../output/cython/foo.pyi
   :language: python
   :caption:
   :lines: 1-

.. literalinclude:: ../../../../output/cython/foo.pxd
   :language: cython
   :caption:
   :lines: 1-

Implementation
--------------

.. automodule:: yace.targets.cython.target
   :members:

.. automodule:: yace.targets.cython.pyxgen
   :members:

.. automodule:: yace.targets.cython.pyigen
   :members:

.. automodule:: yace.targets.cython.cygen
   :members:
