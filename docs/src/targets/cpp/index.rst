.. SPDX-FileCopyrightText: Simon A. F. Lund <os@safl.dk>
..
.. SPDX-License-Identifier: GPL-2.0-only

.. _sec-targets-cpp:

cpp
===

The C++ target, ``cpp``, generates the idiomatic C++ layer of the API, into
``<output>/cpp``. Its raw layer is the C API, which C++ includes as it is, so
the target also emits the C API into ``<output>/capi``, as the C target does:

``<prefix>.hpp``
  The layer, header-only, including ``lib<prefix>.h``. It needs C++20, or
  C++17 where the option ``std`` says so, see :ref:`sec-targets-cpp-std`.

``<prefix>_check.cpp``
  The check, not part of the API: it asserts the layout of the records, and
  prints a zeroed instance of every record, through the layer, as YAML or JSON.

The check is built with ``$CXX``, by default ``c++``, as the standard the layer
is generated for, with all warnings as errors, and run; **yace** then parses what it printed, as YAML and
as JSON. The check asserts the layout of the C API's records, which the layer
uses, as the C check does.

.. _sec-targets-cpp-std:

The C++ standard
----------------

The option ``std`` names the standard that the layer and the check are
generated for: ``c++20``, the default, or ``c++17``, given as
``--target-option cpp.std=c++17``. The layer for C++17 is for a program that
is built as C++17, and it also compiles as C++20.

``std::span`` is all that the layer takes from C++20. The layer for C++17
declares a class of its own instead, ``detail::span``, in the namespace of the
layer, and names it wherever the layer for C++20 names ``std::span``. A span
converts from what ``std::span`` converts from: a ``std::vector``, a
``std::array``, a C array, another span, a pointer and a length in braces,
``{data, size}``, and ``{}`` for none. It has ``data()``, ``size()``,
``size_bytes()``, ``empty()``, ``operator[]``, ``front()``, ``back()``,
``begin()``, ``end()``, ``first()``, ``last()`` and ``subspan()``. It has no
static extent, no reverse iterators, and no ``std::as_bytes()``. A call
written with those conversions and members compiles against both layers.
``std::span(buffer)``, which deduces the type of the element, compiles only
against the layer for C++20.

The alternative was a pointer and a length for each array. With that, a
function that fills a buffer returns a count instead of the part of the buffer
it wrote, a caller with a ``std::vector`` passes ``data()`` and ``size()``
itself, and every signature with an array differs between the two standards.
With the class, the two layers differ in the name of one type.

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

Buffers
  A buffer that ``<stem>_alloc`` allocates, see the buffer pattern in
  :ref:`sec-ir-csubset`, is returned as a ``foo::buffer``, a move-only class,
  a ``std::optional`` where ``@nullable``, and otherwise ``std::bad_alloc`` is
  thrown where the function returns NULL: ``dev.buf_alloc(4096)``. ``data()``
  and ``size()`` are its address and size in bytes, and ``realloc(nbytes)``
  resizes it with ``<stem>_realloc``. Destroying it frees it with
  ``<stem>_free``, which is given the arguments it was allocated with; neither
  has a name of its own in the layer. The handles it was allocated with must
  outlive it. The memory may be a device's, such as GPU memory, which the CPU
  cannot read, and nothing in the API says which; ``bytes()``, the memory as a
  span of ``std::byte``, is for memory of the host only. The class is
  ``buffer_`` where the namespace or the C API has the name ``buffer``.

Registrations
  Memory that ``<stem>_register`` registers, see the registration pattern in
  :ref:`sec-ir-csubset`, is given as a span of ``std::byte``, whose size is
  the size: ``dev.buf_register(memory)``. The function returns a
  ``foo::registration``, a move-only class whose ``memory()`` is the span.
  Destroying it, or calling ``unregister()``, which throws where
  unregistering fails, unregisters the memory with ``<stem>_unregister``,
  which has no name of its own in the layer. The memory, and the handles it
  was registered with, must outlive it. The class is ``registration_`` where
  the namespace or the C API has the name ``registration``.

Errors
  A function documented ``@errno`` throws ``std::system_error``, of the
  ``std::generic_category()``, when it returns a negative errno. One returning
  ``int`` returns nothing otherwise; one returning another integer, such as a
  count, a ``std::size_t``. Where the meta names the function of the library
  that returns the message of the call that failed last, as ``errmsg:
  foo_errmsg``, the layer calls it when a function has failed, and throws
  ``detail::failure``, a ``std::system_error`` whose ``what()`` is the name of
  the function and the message: ``foo_point_add: the handle 'points' holds 8
  points, as many as it can``. ``code()`` is the errno either way, and a
  handler of ``std::system_error`` catches the exception. ``what()`` does not
  add the text of the errno to the message, as ``std::system_error`` would,
  since the message of a library may end in that text already. Where the
  function returns NULL or ``""``, ``what()`` is the name of the function and
  the text of the errno, as without ``errmsg``.

Results
  What a function writes through an ``[out]`` pointer is returned rather than
  passed, several as a ``std::tuple``. An ``[out]`` array is written to a
  ``std::span`` the caller gives, whose size is the capacity, and the part
  written is returned, as a ``std::span`` of as many elements as the function
  says it wrote; nothing is allocated. A returned string is a
  ``std::string_view``, a ``std::optional`` of one where ``@nullable``, borrowed
  from the handle or the library. A returned pointer to a record is a copy of
  it, a ``std::optional`` where ``@nullable``.

Arguments
  A string is a ``const std::string &``, or a ``const char *`` where
  ``@nullable``. An array read through a pointer is a ``std::span``; spans
  sharing one length must be as long, or ``std::invalid_argument`` is thrown; an
  empty one, ``{}``, gives NULL where ``@nullable``. A ``void *`` ``@arrparam``
  is a ``std::span`` of ``std::byte``. The size of a ``@recparam`` record is not
  given; the layer passes ``sizeof`` of the record's type. A handle given is a
  reference to its class, a pointer where ``@nullable``, to ``const`` where the
  C parameter points to const. A pointer to a record or value is a reference, or
  the pointer where ``@nullable``. A callback is any callable, called through a
  ``noexcept`` trampoline with the ``void *`` context, so an exception thrown by
  it terminates, as it cannot cross C; the pointers to records it receives are
  references. A ``@nullable`` callback has an overload taking ``nullptr``. One
  of ``@lifetime once`` (see :ref:`sec-ir-lifetimes`) is moved to the heap and
  deleted once called, or when the call fails; one of ``@lifetime handle`` is
  kept by the handle, unless the call fails, until it is closed, and for good
  where destroying it fails or nothing destroys it, as C may still hold it.

Records and enums
  The records are named without the prefix, ``foo::point``, the C records
  themselves. ``foo::yaml()`` and ``foo::json()`` print a record, as the C
  API's pretty-printers print it, without calling them, and ``operator<<``
  prints its YAML. Each part of a field of bits, see :ref:`sec-ir-csubset`, is
  read by a function of the namespace overloaded on the record,
  ``foo::code_type(status)``, and written by another,
  ``foo::set_code_type(status, value)``, which throws
  ``std::out_of_range`` for a value that does not fit the part's bits; the
  records being C's, they have no methods. Each enum is an
  ``enum class``, its members without the prefix of the enum, in lower case:
  ``FOO_SHAPE_POINT`` is ``foo::shape::point``. ``foo::name()`` is the C name
  of a value, none when it has none.

The comment of a function is that of the C function, whose text may name a
parameter that the signature does not have: a count that is the size of a
span, the size of a ``@recparam`` record, which is that of the record's type,
or an ``[out]`` pointer whose value is returned. yace cannot reword the
text, so the comment gets a ``@note`` that says what the signature has for
each such parameter that the text names in quotes: ``In this signature: 'max'
is the size of 'entries'; 'remaining' is returned.``

A constructor whose name without the handle's is a C++ keyword keeps the name
of the handle: ``foo_req_new()`` is ``foo::req_new()``. Any other name that is
a C++ keyword gets a trailing underscore, as does a method named
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
