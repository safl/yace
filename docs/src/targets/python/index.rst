.. _sec-targets-python:

python
======

The Python target, ``python``, generates bindings of the API through
:py:mod:`ctypes`, into ``<output>/python``:

``<prefix>.py``
  The bindings, a module with no dependencies outside the standard library;
  ``<prefix>_.py`` where the prefix names a module of the standard library,
  such as ``zlib``, which the bindings would otherwise hide or be hidden by.

``<prefix>_check.py``
  The check, not part of the API: it asserts that every record has the size,
  alignment and field offsets recorded in the IR, then prints a zeroed instance
  of every record, as YAML or JSON.

``<prefix>.pxd``, ``lib<prefix>.h``
  The C API for Cython, see :ref:`sec-targets-python-cython`, and the header it
  declares, as the C target emits it.

``<prefix>_check.pyx``
  The check of the ``.pxd``, not part of the API: it assigns each name the
  ``.pxd`` declares to what the ``.pxd`` says its type is, or its address to a
  pointer to that.

The check is run with the Python running **yace**. It loads no library, so it
needs none built. **yace** then parses what it printed, as YAML and as JSON. As
for the C API, the layout is asserted only on the platform it was recorded on.
Where that Python has Cython, **yace** also translates the check of the
``.pxd`` and compiles what Cython made of it with the header, so a declaration
that disagrees with the header fails to compile. A bit-field is the exception:
it has no address to take, so the integer type the ``.pxd`` gives it is not
checked. Nothing runs it. Where that
Python has no Cython, **yace** warns that the ``.pxd`` is not checked, and the
check does not fail.

The bindings
------------

Names are those of the C API, so its documentation applies, as with the modules
of Python's own library that bind C APIs. Only types are renamed, to CamelCase,
as Python names classes: ``struct foo_point`` is ``FooPoint``, as is ``typedef
struct foo_point foo_point;``, the callback type ``foo_visit_cb`` is
``FooVisitCb``. Where two C names would get the same
Python name, both keep their C names. A name that is a Python keyword gets a
trailing underscore.

Constants
  ``#define`` constants, by their names.

Enumerations
  Each enum is an :py:class:`enum.IntEnum`, with members by their C names, also
  given as constants of the module, as :py:mod:`signal` and :py:mod:`socket`
  do. ``Kind(value).name`` is the name of a value.

Records
  Each struct and union is a :py:class:`ctypes.Structure` or
  :py:class:`ctypes.Union`. Each that has fields has the pretty-printers:
  ``to_dict()``, its fields as plain values, ``fpr(stream, obj, flags)`` and
  ``pr(obj, flags)``, printing ``obj``, an instance, a pointer to one, or
  ``None``, as the C API's ``<name>_fpr()`` and ``<name>_pr()`` do. ``str()`` of
  a record is its YAML, and ``repr()`` is as its constructor is called,
  ``FooPoint(x=3, y=4)``: arrays as lists, a field typed as an enum by the name
  of its member, every member of a union. An opaque record is an empty
  structure, used through pointers. Each part of a field of bits, see :ref:`sec-ir-csubset`, is a
  property, ``<field>_<part>``, such as ``status.code_type``, reading the part
  shifted down and writing it in its place, raising :py:class:`ValueError` for a
  value that does not fit its bits; the field itself is there as before.

Callbacks
  A function pointer type is a :py:func:`ctypes.CFUNCTYPE`. The caller keeps
  the callback alive as long as C may call it.

Functions
  Each function is a Python function of the same name and parameters. A
  ``const char *`` parameter takes a :py:class:`str`, or :py:class:`bytes`, and
  a ``const char *`` returned is a :py:class:`str`. A pointer returned is
  ``None`` when NULL. Out-parameters are passed with :py:func:`ctypes.byref`, as
  in C; a record passed where a pointer to it is expected is passed by
  reference.

The idiomatic layer
-------------------

Over the raw functions, the module has an idiomatic layer, from what the header
says beyond C, see :ref:`sec-ir-csubset`. Its names lose the prefix of the
API:

Handles
  An opaque record is a class, named without the prefix: ``struct foo_handle``
  is ``Handle``. Its constructor is a function of the module, ``foo.open()``,
  its destructor the method ``close()``, raising ``OSError`` where it has
  ``@errno``, also called on leaving a ``with``-block, or when collected, and
  the functions taking it first are its methods:
  ``handle.add(point)`` calls ``foo_add(handle, point)``.

Errors
  A function documented ``@errno`` raises :py:class:`OSError`, with the errno,
  when it returns a negative value. One returning ``int`` returns nothing
  otherwise; one returning another integer, such as a count, returns it.

Results
  What a function writes through an ``[out]`` pointer is returned rather than
  passed: ``foo.figure_fill(shape)`` returns the figure. An ``[out]`` array is
  returned as a list of as many elements as the function says it wrote.

Arguments
  An array read through a pointer is given as a sequence, its ``@len`` count
  not given; sequences sharing one count must be as long, or ``ValueError`` is
  raised. One that is ``[in,out]`` is a list, written back. A ``void *`` with a
  ``@len`` is bytes, a ``bytearray`` written in place where ``[in,out]``. A
  handle given is its class. A callback is given as any callable, without the
  ``void *`` context, which the layer gives C; pointers to records it receives
  are the records, and strings ``str``. One of ``@lifetime once`` is kept until
  called, or until the call fails; one of ``@lifetime handle``, unless the call
  fails, until the handle is closed or collected, and for good where destroying
  it fails or nothing destroys it, as C may still hold it; a handle the layer
  only borrows keeps them, as nothing tells it when the handle is destroyed. A
  ``@nullable`` parameter defaults to ``None`` where those after it do too.

The idiomatic layer uses the raw functions and records, so the two mix: a record
returned by one is given to the other. A name the idiomatic layer would take
from the raw one, where there is no prefix to strip, or that two functions would
share, keeps the C name. A module-level function named ``ctypes`` or ``enum``,
or beginning with ``_``, and a constructor that keeps its C name, get the suffix
``_``; so does a parameter named as what the function names, such as ``self``,
``ret``, a raw function or a class, or beginning or ending with ``_``, so no two
parameters share a name.

The library is loaded on the first call of a function. Its path is the
environment variable ``<PREFIX>_LIBRARY``, or the library is found by
:py:func:`ctypes.util.find_library` from the name in the IR's meta, without the
``lib`` prefix.

A variadic function is not bound: calling one through ctypes is not portable.
Types declared outside the headers, such as ``FILE``, are empty structures,
usable through pointers. These are outside the C subset; the diagnostics of the
header say so.

.. _sec-targets-python-cython:

From Cython
-----------

The module is the one Python API. For Cython code calling C in its own hot
loops, ``<prefix>.pxd`` declares the C API, its records, enums, defines and
functions, from the same IR, in a ``cdef extern`` block of ``lib<prefix>.h``,
``nogil``, so the functions are called also without the GIL:

.. code-block:: cython

   cimport foo as lib

   def count(int times):
       cdef lib.foo_handle *handle = NULL
       if lib.foo_open(b"loop", &handle):
           raise OSError("foo_open() failed")
       ...

The ``.pxd`` is named as the module, and beside it, so ``cimport foo`` finds the
declarations and ``import foo`` the ctypes module; Cython code may do both.
Cimporting it as another name, such as ``lib``, also works for a prefix that
Cython reserves, such as ``api``. Names are those of the C API, but for those
Cython reserves, such as a function named ``include``, and the tags of records
and enums named as a function, define, enum member or typedef, which C keeps
apart and Cython does not: these are declared with a trailing ``_`` and their C
name, ``int include_ "include"(int cdef_)``. A flexible array is left out, as
Cython has none, and a comment says so.

A user's extension is built with ``<output>/python`` on the include path of
both Cython, for the ``.pxd``, and the C compiler, for the header, and linked
against the library; with setuptools:

.. code-block:: python

   from Cython.Build import cythonize
   from setuptools import Extension, setup

   extension = Extension(
       "loop", ["loop.pyx"], include_dirs=["output/python"], libraries=["foo"]
   )
   setup(ext_modules=cythonize([extension], include_path=["output/python"]))

``examples/libfoo/checks/cython/check.pyx`` calls libfoo this way, and prints
what it got back, its records from their C fields.

What it brings
~~~~~~~~~~~~~~

``examples/libfoo/bench`` fills a handle with points by ``foo_add_many()``, then
sums the x of every point in six ways, from the idiomatic layer to plain C. A
libfoo handle holds ``FOO_POINTS_MAX`` points, 8, so each way sums them for a
number of rounds; all six must get the same sum. Its ``setup.py`` and
``bench.py`` say how to build and run it; the tests run it with a few rounds,
for the sums, never the timings.

One run on one machine, an AMD Ryzen 7 7840U, with Python 3.12.13, Cython 3.3.1
and libfoo built with ``-O2``, of 200000 rounds, 1600000 points, the best of
five runs of each way:

========================================  ============
Way                                       ns per point
========================================  ============
ctypes, idiomatic ``handle.at()``         660.0
ctypes, raw ``foo_at()``                  450.1
ctypes, ``foo_visit()`` calling Python    227.9
Cython, ``foo_at()`` through the .pxd     1.4
Cython, ``foo_visit()`` calling Cython    1.6
C, ``foo_at()``                           1.4
========================================  ============

Example
-------

.. literalinclude:: 200_yace.cmd
   :language: bash
   :lines: 1-

.. literalinclude:: 300_output.out
   :language: text
   :lines: 1-

The fixture library is called through the raw layer by
``examples/libfoo/checks/python/check.py``, and through the idiomatic layer by:

.. literalinclude:: ../../../../examples/libfoo/checks/python/idiomatic.py
   :language: python
   :caption:
   :lines: 1-

Bindings
~~~~~~~~

.. literalinclude:: ../../../../output/python/foo.py
   :language: python
   :caption:
   :lines: 1-

.. literalinclude:: ../../../../output/python/foo.pxd
   :language: cython
   :caption:
   :lines: 1-

Implementation
--------------

.. automodule:: yace.targets.python.target
   :members:

.. automodule:: yace.targets.python.pygen
   :members:

.. automodule:: yace.targets.python.idiomatic
   :members:

.. automodule:: yace.targets.python.cygen
   :members:
