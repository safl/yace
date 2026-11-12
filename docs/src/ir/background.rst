.. SPDX-FileCopyrightText: Simon A. F. Lund <os@safl.dk>
..
.. SPDX-License-Identifier: GPL-2.0-only

.. _sec-ir-background:

Background
==========

Bindings work when both sides agree on more than a header can show. This page
describes what they must agree on, and what **yace** does about each part. The
rules of the C subset follow from it, see :ref:`sec-ir-csubset`.

C API and C ABI
---------------

The C API is what the header declares: the names of the types and functions,
and what they take and return. It is what a C programmer reads, and what a C
compiler checks a call against.

The C ABI is what the compiled code agrees on. It is the size and alignment of
every type, the offset of every field in a record, and the calling convention:
where the arguments go, and where the result comes back. The header does not
state any of it. The compiler derives it from the header by the rules of the
platform, such as the System V ABI on Linux on x86-64.

A binding in another language does not include the header. It declares the
same types and functions again, in its own language, and the compiled library
only works with it if those declarations have the same ABI. Two declarations
can name the same fields and still lay them out differently, and nothing at
the call says so. A mismatch shows up as wrong values, or as memory written
where it should not be.

**yace** parses the header with libclang, as a compiler of the platform would,
and records in the IR the layout that compiler chose. Every target is checked
against that record, see :ref:`sec-ir-background-checked`.

Memory layout
-------------

A record is laid out in the order of its fields. Each field is placed at an
offset that is a multiple of its alignment. The record is aligned as its most
aligned field, and its size is a multiple of that alignment, so that the
records of an array are each aligned. The alignment of each type is the
platform's: ``uint32_t`` is aligned to 4 bytes on most platforms, but
``double`` and ``int64_t`` are not aligned to 8 on all of them.

The IR records, for every struct and union with fields, its ``size`` and
``align`` in bytes, and for each field its ``offset`` in bits from the start of
the record. The meta of the IR records the platform the layout is valid for,
as ``abi``, such as ``Linux-x86_64``.

The width of ``int``, ``long`` and the others is up to the platform too. The
targets map them to the C types of their language, so a binding has the
widths of the platform it is built on, as C does; see
:ref:`sec-ir-csubset`.

Padding
-------

Padding is the bytes the compiler leaves unused to align what follows. There
is padding between fields, before a field that is more aligned than the end of
the one before it, and at the end of the record, to round its size up to its
alignment.

For example, this record has three bytes of padding after ``kind`` and two at
the end, so its size is 12 and not 7:

.. literalinclude:: pad.h
   :language: c
   :caption:

Given to **yace**:

.. literalinclude:: 100_background.cmd
   :language: bash

the IR records the layout:

.. literalinclude:: ../../../output/pad/pad.yaml
   :language: yaml
   :start-at: - key: struct_decl

The targets do not write the padding out as fields. Each declares the record
in the way its language lays out records as C does: ``#[repr(C)]`` in Rust,
``extern struct`` in Zig, ``ctypes.Structure`` in Python, and the record as it
is in C and C++. The padding then follows from the fields, as it does in C, and
the check asserts that it did.

Packing
-------

Packing removes the padding, by lowering the alignment of a record or its
fields, with ``__attribute__((packed))`` or ``#pragma pack``. Its counterpart,
``__attribute__((aligned(n)))``, raises the alignment, and adds padding. None
of these is C99. Each compiler spells them its own way, and not every target
language can express each of them.

A record declared with ``__attribute__((packed))`` is recorded as ``packed``
in the IR, with the layout the compiler chose, and every target declares it
packed: the C API with the attribute, and so C++; Python with ``_pack_ = 1``;
Rust with ``#[repr(C, packed)]``; Zig as an ``extern struct`` whose fields are
each ``align(1)``. Go aligns every field, so a packed record is its bytes, each
field read and written by a copy, through a getter and a setter. A field of a
packed record may not be aligned for its type, so a reference to it, or its
address, may not be used as one to an aligned value: the printers of every
target read such a field by a copy. A packed record is in the subset.

The aligned attribute is not carried to any target. On a record, it is
reported by the attribute rule; ``#pragma pack``, and an attribute on a field,
are not reported. Where the layout is not checked, see
:ref:`sec-ir-background-checked`, the bindings of such a record are wrong.
Only the diagnostic of the attribute says so, and for ``#pragma pack`` there is
none.

Ctypes packs bit-fields only as MSVC does, which is not as GCC packs them, so
in Python a packed record with bit-fields keeps only its size and alignment, as
an array of bytes, as the other targets keep any record with bit-fields, see
below.

Bit-fields
----------

C leaves most of the layout of a bit-field to the compiler: the order of the
bits within a unit, whether a bit-field may span two units, and what an
unnamed one does to alignment. Rust has no bit-fields, and the packed structs
of Zig are not laid out as C bit-fields are.

The IR records the width of a bit-field as ``bits``, and its offset in bits.
Bit-fields are reported by the bitfield rule. The C API keeps them as they are,
and Python keeps them as ctypes bit-fields where ctypes lays them out as C
does. Elsewhere, a record with bit-fields keeps only its size and alignment,
as an array of bytes. The checks of C, Python and Rust assert the size and
alignment of such a record; that of Zig does not check it. The subset's
alternative is a field of bits, see :ref:`sec-ir-csubset`.

Flexible arrays
---------------

A flexible array member, ``uint8_t data[]``, ends a struct, and adds nothing to
its size but the padding its alignment may need. ISO C allows a record with
one in no array and no struct, though GCC and Clang accept both, as an
extension. A flexible array member is reported by the flexible-array rule, and
so is a field holding a record with one. A flexible array of such records is
left out of its record, and the record kept, where leaving it out keeps the
alignment of the record, and so its layout. Otherwise, and for any other field
holding such a record, the record is skipped, as is what uses it.

Calling conventions
-------------------

A calling convention says how a call passes its arguments and its result: in
which registers, in what order on the stack, and who cleans up after. Each
platform has a default one. The FFI of every target language implements it
for integers, floating point and pointers, which is all the subset passes.

Records by value are where the conventions differ most. Depending on its size
and its fields, a record may be split across registers, passed on the stack,
or passed through a hidden pointer, and the rules differ by platform. Passing
a record by value is reported by the record-by-value rule. It is still bound,
in every target, and relies on that language's FFI to implement the
platform's rules for it.

A variadic function passes its variable arguments by other rules again, with
promotions the caller must apply, and on some platforms in other registers
than a fixed parameter. It is reported by the variadic-function rule, and
recorded in the IR as ``variadic``. The C API and the Cython ``.pxd`` declare
it, and the raw layers of Rust and Zig declare it as variadic. The Python module
and the Go package do not bind it, because ctypes and cgo cannot call it, and no
idiomatic layer wraps it.

An enum passed by value is an integer of a type the compiler chooses. The IR
records it as ``underlying`` of the enum; passing one is reported by the
enum-in-signature rule.

**yace** binds every function with the default calling convention of the
platform. An attribute selecting another one, such as ``ms_abi``, is not
carried to any target.

.. _sec-ir-background-checked:

What is checked
---------------

Every target builds a check of what it generated, and runs it. Where the IR was
recorded on the platform it is built on, that is, the ``abi`` of its meta is
the host's, the check asserts the size and alignment of the records with
fields, and the offsets of the fields it can name, against the IR. The check
of the C API asserts them at compile time, for this example:

.. literalinclude:: ../../../output/pad/capi/pad_check.c
   :language: c
   :start-at: _Static_assert
   :end-at: offsetof(pad_sample, count)

The other targets assert the same in their own language. The C++ layer uses
the records of the C API, and its check asserts them as the C check does. Where the ``abi``
differs from the host's, or with ``--no-check``, the layout is not asserted.

No check asserts a calling convention. The fixture exercises them end to end:
it builds the example library and calls it through every target, see
:ref:`sec-targets`. The example library is in the subset, so it passes no
record by value and has no variadic function; nothing exercises those.
