.. _sec-targets-cpp:

cpp
===

The C++ target, ``cpp``, generates the idiomatic C++ layer of the API, into
``<output>/cpp``. Its raw layer is the C API, which C++ includes as it is, so
the target also emits the C API into ``<output>/capi``, as the C target does:

``<prefix>.hpp``
  The layer, header-only, including ``lib<prefix>.h``. It needs C++20, for
  ``std::span``.

``<prefix>_check.cpp``
  The check, not part of the API: it prints a zeroed instance of every record,
  through the layer, as YAML or JSON.

The check is built with ``$CXX``, by default ``c++``, as C++20 with all
warnings as errors, with the pretty-printers of the C API built by ``$CC``, and
run; **yace** then parses what it printed, as YAML and as JSON. The layout is
the C API's, asserted by its check.

The layer
---------

Everything is in a namespace named for the prefix, its names without the
prefix, so nothing clashes with the macros of the C API's ``#define``
constants, which C++ uses as they are. Where the C API declares something named
as the prefix, the namespace is the prefix and ``_cpp``. From what the header
says beyond C, see :ref:`sec-ir-csubset`, and as derived in
:py:mod:`yace.targets.idiom`:

Handles
  An opaque record is a move-only class, named without the prefix, owning the
  pointer by a ``std::unique_ptr`` whose deleter is the destructor:
  ``struct foo_handle`` is ``foo::handle``. Its constructor is a function of the
  namespace, ``foo::open()``, a ``std::optional`` where it has no ``@errno``;
  ``close()`` releases it before it goes out of scope; the functions taking it
  first are its methods, ``const`` where the pointer is to const.
  ``native_handle()``, as ``std::thread`` names it, is the raw pointer, for the
  C API.

Errors
  A function documented ``@errno`` throws ``std::system_error``, of the
  ``std::generic_category()``, when it returns a negative errno. One returning
  ``int`` returns nothing otherwise; one returning another integer, such as a
  count, a ``std::size_t``.

Results
  What a function writes through an ``[out]`` pointer is returned rather than
  passed, several as a ``std::tuple``; an ``[out]`` array as a ``std::vector``
  of as many elements as the function says it wrote. A returned string is a
  ``std::string_view``, a ``std::optional`` of one where ``@nullable``, borrowed
  from the handle or the library. A returned
  pointer to a record is a copy of it, a ``std::optional`` where
  ``@nullable``.

Arguments
  A string is a ``const std::string &``, or a ``const char *`` where
  ``@nullable``. An array read through a pointer is a ``std::span``; spans
  sharing one ``@len`` count must be as long, or ``std::invalid_argument`` is
  thrown; an empty one, ``{}``, gives NULL where ``@nullable``. A ``void *``
  with a ``@len`` is a ``std::span`` of ``std::byte``. A handle given is a
  reference to its class, a pointer where ``@nullable``. A pointer to a record
  or value is a reference, or the pointer where ``@nullable``. A callback is
  any callable, called through a ``noexcept`` trampoline with the ``void *``
  context, so an exception thrown by it terminates, as it cannot cross C; the
  pointers to records it receives are references. A ``@nullable`` callback has
  an overload taking ``nullptr``. One of ``@lifetime once`` is moved to the
  heap and deleted once called, or when the call fails; one of
  ``@lifetime handle`` is kept by the handle, unless the call fails, until it
  is closed, and for good where destroying it fails or nothing destroys it, as
  C may still hold it.

Records and enums
  The records are named without the prefix, ``foo::point``, the C records
  themselves. ``foo::yaml()`` and ``foo::json()`` print a record, by the C
  API's pretty-printers, and ``operator<<`` prints its YAML. Each enum is an
  ``enum class``, its members without the prefix of the enum, in lower case:
  ``FOO_SHAPE_POINT`` is ``foo::shape::point``. ``foo::name()`` is the C name
  of a value, none when it has none.

A name that is a C++ keyword gets a trailing underscore, as does a method named
``native_handle``, ``deleter`` or as a handle class, and a parameter named as
what its function names unqualified, such as ``ret``, the local of the result,
a C name or a handle class, or ending in ``_``, so no two parameters share a
name. A type or function whose name would hide a C name, or one the namespace
declares or uses, ``yaml``, ``json``, ``name``, ``detail`` and ``std``, gets
``_handle`` for a handle class and ``_`` otherwise; a function also gets ``_``
where an enum class or handle class has its name. A record has no alias where a
function has its name, or where its tag has no prefix: its C name is the one.

Example
-------

.. literalinclude:: 200_yace.cmd
   :language: bash
   :lines: 1-

.. literalinclude:: 300_output.out
   :language: text
   :lines: 1-

The fixture library is called through the layer by
``examples/libfoo/checks/cpp/check.cpp``:

.. literalinclude:: ../../../../examples/libfoo/checks/cpp/check.cpp
   :language: c++
   :caption:
   :lines: 1-

The layer
~~~~~~~~~

.. literalinclude:: ../../../../output/cpp/foo.hpp
   :language: c++
   :caption:
   :lines: 1-

Implementation
--------------

.. automodule:: yace.targets.cpp.target
   :members:

.. automodule:: yace.targets.cpp.cppgen
   :members:
