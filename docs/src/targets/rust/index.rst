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
Rust 1.81 or later, where a panic unwinding out of a callback aborts.

The bindings
------------

Names are those of the C API, so its documentation applies. Only types are
renamed, to CamelCase, as Rust names types: ``struct foo_point`` is
``FooPoint``, and ``typedef struct foo_point foo_point;`` is that type. Where
two C names would get the same Rust name, both keep their C names. A name that
is a Rust keyword is a raw identifier, ``r#type``, or, for those that cannot
be, gets a trailing underscore, ``self_``. So does a parameter named ``ret``,
the local of the result, ``Some``, ``None``, ``Ok`` or ``Err``, as a type of
the crate, or ending in ``_`` or ``_trampoline``, so no two parameters share a
name.

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
  be constructed, used through pointers. Each part of a field of bits, see
  :ref:`sec-ir-csubset`, has a getter and a setter, ``code_type()`` and
  ``set_code_type(value)``, of the field's type; the setter panics on a value
  that does not fit the part's bits. The field itself is there as before; a
  getter of a union's field is safe, as every value of an integer is one.

Callbacks
  A function pointer type is an ``Option`` of an ``unsafe extern "C" fn``, the
  nullable function pointer of Rust.

Functions
  Declared in an ``extern "C"`` block, by their C names and parameters, and so
  unsafe to call, as calling C is. A pointer to const is ``*const``, any other
  ``*mut``.

The idiomatic layer
-------------------

Over the raw functions, the module ``safe`` is the idiomatic layer, from what
the header says beyond C, see :ref:`sec-ir-csubset`. Its names lose the prefix
of the API:

Handles
  An opaque record is a type owning a pointer to it, named without the prefix:
  ``struct foo_handle`` is ``safe::Handle``, with ``Handle`` appended where the
  name is a raw type's or one the module uses from std, as ``Option``. Its
  constructor is an associated function, ``Handle::open()``, returning an
  ``Option`` where it has no ``@errno``; its destructor is called when it is
  dropped, or by ``close()``; the functions taking it first are its methods,
  taking ``&self`` where the pointer is to const and it keeps no closure,
  ``&mut self`` otherwise. ``as_ptr()`` is the raw pointer, for the raw
  functions; a method named ``as_ptr`` is ``as_ptr_()``. It is neither ``Send``
  nor ``Sync``: the header does not say it may be.

Errors
  A function documented ``@errno`` returns ``io::Result``, its error made by
  ``io::Error::from_raw_os_error()``. One returning ``int`` returns ``()``
  otherwise; one returning another integer, such as a count, a ``usize``.

Results
  What a function writes through an ``[out]`` pointer is returned rather than
  passed; an ``[out]`` array as a ``Vec`` of as many elements as the function
  says it wrote. A returned string is a ``&CStr`` borrowed from the handle, from
  the one reference given, or ``'static`` when none is; with more than one, the
  function is ``unsafe``. A returned pointer to a record is a copy of it, an
  ``Option`` where ``@nullable``.

Arguments
  An array read through a pointer is a slice; slices sharing one ``@len`` count
  must be as long, or the call panics; a ``@nullable`` one is an ``Option``,
  ``None`` passing NULL. A ``void *`` with a ``@len`` is a slice of ``u8``. A
  handle given is a reference to its type. A callback is a ``&mut dyn FnMut``
  closure, called through a generated trampoline with the ``void *`` context;
  the pointers to records it receives are references. One of ``@lifetime once``
  is a ``Box<dyn FnOnce>``, freed once called, or when the call fails; one of
  ``@lifetime handle`` a ``Box<dyn FnMut>``, which the handle keeps, unless
  the call fails, until it is dropped, and for good where destroying it fails
  or nothing destroys it, as C may still hold it. A ``@nullable`` pointer is an
  ``Option``.

A function is safe where everything a caller gives is checked by the types: a
function taking a raw pointer, or a record holding one, is ``unsafe``, as safe
Rust can make those point anywhere. A panic in a closure aborts, as unwinding
cannot cross C.

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

The fixture library is called through the raw layer by
``examples/libfoo/checks/rust/check.rs``, and through the idiomatic layer by:

.. literalinclude:: ../../../../examples/libfoo/checks/rust/idiomatic.rs
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

.. automodule:: yace.targets.rust.idiomatic
   :members:
