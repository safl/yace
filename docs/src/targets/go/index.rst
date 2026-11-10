.. SPDX-FileCopyrightText: Simon A. F. Lund <os@safl.dk>
..
.. SPDX-License-Identifier: GPL-2.0-only

.. _sec-targets-go:

go
==

The Go target, ``go``, generates a Go module of one package binding the API
through cgo, into ``<output>/go``:

``go.mod``
  The module, named as the prefix, ``foo``, and needing Go 1.22.

``<prefix>.go``
  The bindings, in two layers.

``<prefix>_link.go``
  What links the library, ``-l<name>``, the name of the API without ``lib``.
  Built with the tag ``<prefix>_no_link``, the package links nothing, for what
  uses only its types.

``<prefix>_no_link.c``
  What the tag links in place of the library: each function by its name only,
  aborting when called, as cgo refers to every function the package calls.

``<prefix>_callbacks.c``
  The C trampolines of the callbacks given as Go functions, when there are any.

``lib<prefix>.h``
  The C API, as the C target emits it, which the package includes.

``check/main.go``
  The check, not part of the API: it does not compile unless every record has
  the size, alignment and field offsets recorded in the IR, then prints a
  zeroed instance of every record, as YAML or JSON.

The package needs cgo, and so a C compiler. **yace** vets the package and the
check, with ``$GO``, by default ``go``, and the tag ``<prefix>_no_link``, so the
library need not be built, then builds and runs the check, and parses what it
printed, as YAML and as JSON. As for the C API, the layout is asserted only on
the platform it was recorded on.

A program uses the package by requiring the module, with a ``replace``
directive giving where it was generated, and links the library found through
``CGO_LDFLAGS``, such as ``-L/path/to/lib``. Headers the API includes are found
through ``CGO_CFLAGS``.

The raw layer
-------------

The C API as C has it, by its C names, which Go exports only from an upper-case
letter: ``foo_open()`` is ``Foo_open()``, ``FOO_MAGIC`` stays ``FOO_MAGIC``.
Each function converts what it is given and calls the C function through cgo.
cgo's own types are of no use outside the package, so the records are Go structs
of the C layout, named in CamelCase, ``struct foo_point`` as ``FooPoint``, with
their fields exported, ``Ncorners``; the layout is what the check asserts.

A union is its bytes, aligned as the union, and a method per member returning a
pointer to the member in them, ``*value.I() = -1``, as Go has no unions. A
record with bit-fields keeps only its size and alignment, as in Zig. A packed
record, which cgo does not declare the unaligned fields of, is its bytes, with
a getter and a setter per field reading and writing a copy of it, ``At()`` and
``SetAt(value)``, as Go aligns every field. A getter, also of a part of a
field of bits, takes the record by value, so getters chain, ``Many()[1].At()``;
the garbage collector does not see
a pointer set through a setter. A flexible
array, last in a struct, is left out, as a struct ending in a zero-sized field
is padded in Go; a comment says so. An opaque record is a struct of no fields,
usable only through pointers, as is a type declared outside the headers.

Pointers are Go pointers, which may point to C memory; ``void *`` and function
pointers are ``unsafe.Pointer``, and a callback typedef a type of its own over
it. C's ``long`` and ``unsigned long`` are ``CLong`` and ``CULong``, as wide as
the platform's; ``size_t`` and ``uintptr_t`` are ``uintptr``, ``ssize_t``,
``ptrdiff_t`` and ``intptr_t`` are ``int``. Each enum is an integer type, not a
closed set, its members constants by their C names, with ``Name()`` the C name
of a value and whether it has one, and ``String()`` the name or the type and the
value.

What cgo cannot call is not bound, and a comment in its place says why: a
variadic function, one named as a Go keyword, or one taking or returning by
value a type Go knows only the name of.

Every struct and union has printers of its own, not calling the C API's:
``Fpr(w, flags)`` prints to an ``io.Writer``, also through a nil pointer, as
``<name>_fpr()`` does, and ``String()``, the ``fmt.Stringer`` of the record, is
its YAML. They print what the C API's pretty-printers print, floats as C's
``%g`` prints them, except for a record with bit-fields: Go keeps it as its
bytes, so it has no printers, and a record holding one prints it as ``null``,
where the C printers print its fields. Each part of
a field of bits, see :ref:`sec-ir-csubset`, has a getter and a setter,
``CodeType()`` and ``SetCodeType(value)``, of the field's type, the setter
panicking on a value that does not fit the part's bits. A name the struct has
already, as a field or a printer, gets a trailing underscore.

Memory given to C must hold no Go pointers, as cgo requires: a record given by
a pointer may point to C memory, not to Go memory. cgo checks it as it passes
the record.

The idiomatic layer
-------------------

Over the raw one, from what the header says beyond C, see
:ref:`sec-ir-csubset`, and as derived in :py:mod:`yace.targets.idiom`. Its
functions are named in CamelCase, without the prefix:

Handles
  An opaque record is a struct holding the pointer, named without the prefix:
  ``struct foo_handle`` is ``Handle``. Its constructor is a function of the
  package, ``foo.Open()``, returning a ``*Handle``, nil where it has no
  ``@errno`` and C gave none; its destructor is a method, ``Close()``, for
  ``defer handle.Close()``; the functions taking it first are its methods.
  ``Ptr()`` is the raw pointer. A handle given otherwise is a ``*`` of its
  struct, nil passing NULL.

Errors
  A function documented ``@errno`` returns an ``error`` last, a
  ``syscall.Errno`` wrapped with the name of the C function, so
  ``errors.Is(err, syscall.EINVAL)`` holds for ``-EINVAL``. One returning ``int``
  returns only the ``error``; one returning another integer, such as a count,
  an ``int`` before it.

Results
  What a function writes through an ``[out]`` pointer is returned rather than
  passed. An ``[out]`` array is written to a slice the caller gives, as
  ``io.Reader`` does, and the part written is returned. A returned string is a
  Go ``string``, copied. A returned pointer to a record is a copy of it, with
  whether there was one where ``@nullable``,
  ``point, ok := handle.PointGet(1)``.

Arguments
  A string is a ``string``, a ``*string`` where ``@nullable``, nil passing NULL;
  it is copied to C memory for the call, up to its first NUL. An array read
  through a pointer is a slice; slices sharing one ``@len`` count must be as
  long, or the call panics; a nil slice passes NULL. A ``void *`` with a
  ``@len`` is a ``[]byte``.

Callbacks
  A callback is a Go function, of a type named for the callback typedef,
  ``FooVisitCbFunc``, without the ``void *`` context, its pointers to records
  Go pointers to C memory valid during the call, its strings copied. cgo lets C
  hold no Go pointer, so the function is kept in a ``runtime/cgo.Handle``, held
  in C memory given as the context, which a C trampoline gives to the Go
  function the package exports for the callback. It is released as its
  ``@lifetime`` says: when the call returns, for ``call``; once it has been
  called, for ``once``; when the handle is destroyed, for ``handle``, and never
  where the destructor fails or nothing destroys the handle, as C may still
  hold it. One the call fails to take, by its ``@errno``, is released at once.
  A ``@nullable`` callback may be nil, passing NULL. A panic in the function
  unwinds the C frames that called it, which C does not expect.

A call that has no idiomatic form, as the raw layer does not bind it or what it
writes has no fields to return, has a comment in its place naming the raw
function. A name that is a Go keyword or a predeclared identifier, such as
``len``, a package the code uses, such as ``unsafe``, a name of the package, or
a local of the layer, such as ``ret``, gets a trailing underscore as a
parameter, as does a function named as one before it in the package, or a
method named ``Ptr``.

Example
-------

.. literalinclude:: 200_yace.cmd
   :language: bash
   :lines: 1-

.. literalinclude:: 300_output.out
   :language: text
   :lines: 1-

The fixture library is called through the idiomatic layer, and the raw one for
what the idiomatic one does not take, by
``examples/libfoo/checks/go/main.go``:

.. literalinclude:: ../../../../examples/libfoo/checks/go/main.go
   :language: go
   :caption:
   :lines: 1-

Bindings
~~~~~~~~

.. literalinclude:: ../../../../output/go/foo.go
   :language: go
   :caption:
   :lines: 1-

Implementation
--------------

.. automodule:: yace.targets.go.target
   :members:

.. automodule:: yace.targets.go.ggen
   :members:

.. automodule:: yace.targets.go.raw
   :members:

.. automodule:: yace.targets.go.idiomatic
   :members:
