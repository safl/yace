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

The check is run with the Python running **yace**. It loads no library, so it
needs none built. **yace** then parses what it printed, as YAML and as JSON. As
for the C API, the layout is asserted only on the platform it was recorded on.

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
  a record is its YAML. An opaque record is an empty structure, used through
  pointers.

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

The library is loaded on the first call of a function. Its path is the
environment variable ``<PREFIX>_LIBRARY``, or the library is found by
:py:func:`ctypes.util.find_library` from the name in the IR's meta, without the
``lib`` prefix.

A variadic function is not bound: calling one through ctypes is not portable.
Types declared outside the header, such as ``FILE``, are empty structures,
usable through pointers. These are outside the C subset; the diagnostics of the
header say so.

Example
-------

.. literalinclude:: 200_yace.cmd
   :language: bash
   :lines: 1-

.. literalinclude:: 300_output.out
   :language: text
   :lines: 1-

The fixture library is called through these bindings by
``examples/libfoo/checks/python/check.py``:

.. literalinclude:: ../../../../examples/libfoo/checks/python/check.py
   :language: python
   :caption:
   :lines: 1-

Bindings
~~~~~~~~

.. literalinclude:: ../../../../output/python/foo.py
   :language: python
   :caption:
   :lines: 1-

Implementation
--------------

.. automodule:: yace.targets.python.target
   :members:

.. automodule:: yace.targets.python.pygen
   :members:
