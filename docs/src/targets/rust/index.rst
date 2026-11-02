.. _sec-targets-rust:

rust
====

The Rust target, ``rust``, generates a crate binding the API, in the manner of
a ``-sys`` crate, into ``<output>/rust``:

``Cargo.toml`` and ``build.rs``
  The crate. The build script links the library, named in the IR's meta without
  the ``lib`` prefix, searching the directory in ``<PREFIX>_LIB_DIR`` when set.
  With ``<PREFIX>_NO_LINK`` set it links nothing, for what uses only the types.

``lib.rs``
  The bindings, using nothing outside the standard library.

``check.rs``
  The check, an example of the crate rather than part of it: it asserts at
  compile time that every record has the size, alignment and field offsets
  recorded in the IR, then prints a zeroed instance of every record, as YAML or
  JSON.

The check is built with ``$CARGO``, by default ``cargo``, offline, and run;
**yace** then parses what it printed, as YAML and as JSON. It calls no function
of the library, so needs it neither built nor linked. As for the C API, the
layout is asserted only on the platform it was recorded on. The crate needs
Rust 1.77 or later, for C string literals and ``offset_of!``.

The bindings
------------

Names are those of the C API, so its documentation applies. Only types are
renamed, to CamelCase, as Rust names types: ``struct foo_point`` is
``FooPoint``, and ``typedef struct foo_point foo_point;`` is that type. Where
two C names would get the same Rust name, both keep their C names. A name that
is a Rust keyword is a raw identifier, ``r#type``, or, for those that cannot
be, gets a trailing underscore, ``self_``.

Constants
  ``#define`` constants, as ``pub const``: strings as ``&CStr``, integers as
  ``i32``, or ``i64`` or ``u64`` when that does not hold them.

Enumerations
  Each enum is a ``#[repr(transparent)]`` integer newtype, with its members as
  associated constants, also given as constants of the crate. C does not
  restrict an enum to its members, and a Rust enum holding another value is
  undefined behaviour, so an integer it is. ``name()`` is the name of a value,
  ``None`` when it has none.

Records
  Each struct and union is ``#[repr(C)]``, ``Clone`` and ``Copy``, and has a
  ``Default`` of all zeros. Each has the pretty-printers:
  ``fpr(w, obj, flags)`` and ``pr(obj, flags)``, printing ``obj``, or null for
  ``None``, as the C API's ``<name>_fpr()`` and ``<name>_pr()`` do, and
  ``Display``, printing YAML. An opaque record is a zero-sized type that cannot
  be constructed, used through pointers.

Callbacks
  A function pointer type is an ``Option`` of an ``unsafe extern "C" fn``, the
  nullable function pointer of Rust.

Functions
  Declared in an ``extern "C"`` block, by their C names and parameters, and so
  unsafe to call, as calling C is. A pointer to const is ``*const``, any other
  ``*mut``.

A record with bit-fields, which Rust has none of, keeps only its size and
alignment, as an array of bytes, and is not printed. Types declared outside the
header, such as ``FILE``, are opaque types, usable through pointers. These are
outside the C subset; the diagnostics of the header say so.

Example
-------

.. literalinclude:: 200_yace.cmd
   :language: bash
   :lines: 1-

.. literalinclude:: 300_output.out
   :language: text
   :lines: 1-

The fixture library is called through these bindings by
``examples/libfoo/checks/rust/check.rs``:

.. literalinclude:: ../../../../examples/libfoo/checks/rust/check.rs
   :language: rust
   :caption:
   :lines: 1-

Bindings
~~~~~~~~

.. literalinclude:: ../../../../output/rust/lib.rs
   :language: rust
   :caption:
   :lines: 1-

Implementation
--------------

.. automodule:: yace.targets.rust.target
   :members:

.. automodule:: yace.targets.rust.rgen
   :members:
