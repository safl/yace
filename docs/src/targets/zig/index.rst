.. _sec-targets-zig:

zig
===

The Zig target, ``zig``, generates a module binding the API, into
``<output>/zig``:

``<prefix>.zig``
  The bindings, in two layers.

``<prefix>_check.zig``
  The check, not part of the API: it asserts at compile time that every record
  has the size, alignment and field offsets recorded in the IR, then prints a
  zeroed instance of every record, as YAML or JSON.

``<prefix>_compile.zig``
  What has all of the module compiled, as Zig compiles only what is
  referenced.

The module needs Zig 0.16, as Zig's standard library changes between releases,
and libc, as the C API does. **yace** compiles all of the module, with
``$ZIG``, by default ``zig``, then builds and runs the check, and parses what it
printed, as YAML and as JSON. As for the C API, the layout is asserted only on
the platform it was recorded on.

The raw layer
-------------

The C API as C has it, by its C names, as Zig's own translation of C headers
gives it: records as ``extern struct`` and ``extern union``, named in
CamelCase, ``struct foo_point`` as ``FooPoint``, which ``typedef struct
foo_point foo_point;`` also names; opaque records as ``opaque``;
functions as ``extern fn``; pointers as C pointers, ``[*c]T``, except to opaque
types, ``void`` and functions, which are optional pointers; constants by their
names.
Each enum is a non-exhaustive ``enum``, as C does not restrict an enum to its
values, its members in lower case without the prefix of the enum, with
``cName()`` the C name of a value; the members are also constants by their C
names.

Every struct and union has the pretty-printers: ``fpr(w, obj, flags)``,
printing to a ``*std.Io.Writer`` as the C API's ``<name>_fpr()`` does, and
``format()``, for ``"{f}"``, printing YAML. Floats are formatted by libc's
``snprintf()``: Zig rounds a float from its shortest decimal form, C from its
binary one, and the two differ.

Each part of a field of bits, see :ref:`sec-ir-csubset`, has a getter and a
setter, ``codeType()`` and ``setCodeType(value)``, taking and giving an
integer of the part's own width, such as ``u3``, so a value that does not fit
is a compile error, or a checked cast, rather than one written into the bits
beside it. The field itself is there as before. A name the struct has already,
as a field or a printer, gets a trailing underscore.

The idiomatic layer
-------------------

Over the raw one, from what the header says beyond C, see
:ref:`sec-ir-csubset`, and as derived in :py:mod:`yace.targets.idiom`. Its
functions are named in camelCase, without the prefix:

Handles
  An opaque record is a struct holding the pointer, named without the prefix:
  ``struct foo_handle`` is ``Handle``. Its constructor is a function of it,
  ``Handle.open()``, returning an optional where it has no ``@errno``; its
  destructor a method, also as ``deinit``, for ``defer handle.deinit()``, unless
  a method has that name; the functions taking it first are its methods. A
  handle given otherwise is its struct.

Errors
  A function documented ``@errno`` returns an error union, the error that of
  the errno's name: ``-EINVAL`` is ``error.INVAL``. ``errnoOf()`` is the errno
  of such an error. One returning ``int`` returns ``void`` otherwise; one
  returning another integer, such as a count, a ``usize``.

Results
  What a function writes through an ``[out]`` pointer is returned rather than
  passed. An ``[out]`` array is written to a slice the caller gives, as Zig does
  not allocate behind a caller's back, and the part written is returned. A
  returned string is a ``[:0]const u8``, borrowed; a returned pointer to a
  record a copy of it, optional where ``@nullable``.

Arguments
  A string is a ``[*:0]const u8``, optional where ``@nullable``. An array read
  through a pointer is a slice; slices sharing one ``@len`` count must be as
  long, or the call panics; a ``@nullable`` one is optional, ``null`` passing
  NULL. A ``void *`` with a ``@len`` is a slice of ``u8``. A pointer to a
  record or value is a pointer to one, optional where ``@nullable``. A callback
  is a context pointer and a comptime function taking it, called through a
  generated trampoline with the ``void *``; the caller keeps the context as
  long as the callback's ``@lifetime`` says, which its documentation repeats.
  One that is ``@nullable`` is not optional here, the raw function passing
  NULL.

A function named as a declaration of the module, such as ``std``, as a
parameter of its own functions, such as ``flags``, or as a primitive type, such
as ``u8``, gets the suffix ``_``. A parameter that would shadow a declaration, a
local or a primitive type, which Zig does not allow, that is named ``_``, or
that ends in ``_arg`` and underscores, gets the suffix ``_arg``, and ``_`` until
it shadows nothing. A local of the module's own code, such as ``ret`` or ``w``,
gets ``_`` while the C API declares its name, as an enumerator may. A name that
is a keyword is quoted, ``@"type"``.

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
``examples/libfoo/checks/zig/check.zig``:

.. literalinclude:: ../../../../examples/libfoo/checks/zig/check.zig
   :language: zig
   :caption:
   :lines: 1-

Bindings
~~~~~~~~

.. literalinclude:: ../../../../output/zig/foo.zig
   :language: text
   :caption:
   :lines: 1-

Implementation
--------------

.. automodule:: yace.targets.zig.target
   :members:

.. automodule:: yace.targets.zig.zgen
   :members:

.. automodule:: yace.targets.zig.idiomatic
   :members:
