.. _sec-ir-csubset:

The C Subset
============

The header describing an FFI boundary is written in a subset of C99: what can
be described equivalently in C, C++, Python, Rust and Zig. Every place a header
steps outside it is reported, by the rule it breaks, see :ref:`sec-ir-rules`.
This page describes the subset, and why.

What is in it
-------------

Types
  ``void``, ``bool``, ``char``, ``signed char``, ``unsigned char``, ``short``,
  ``int``, ``long``, ``long long`` and their unsigned forms, ``float``,
  ``double``, the fixed-width integers of ``<stdint.h>``, ``intptr_t``,
  ``uintptr_t``, ``size_t``, ``ssize_t`` and ``ptrdiff_t``; pointers to any of
  these, and fixed-length arrays of them, of any dimension.

Records
  ``struct`` and ``union``, each with a tag and defined at the top level. A
  record declared but never defined is opaque, a handle used through pointers.
  A typedef of a record of its own name, ``typedef struct foo foo;``, is that
  record; one of another type, ``typedef struct foo *foo;``, which no binding
  could declare beside the record, is reported, and its type used in its place.

Enumerations
  ``enum``, with a tag, to name and document values.

Functions
  Declarations of functions, with named parameters, taking and returning the
  types above, records by pointer.

Function pointers
  ``typedef``'d, with named parameters, for callbacks.

Constants
  ``#define`` of a string literal or an integer constant expression.

Headers
  ``#include`` of the standard headers above. What another header declares is
  outside the boundary: a type from one is reported as external-type.

Records
-------

Records are how data crosses the boundary. C has many ways of defining them;
only some of them bind well. Nested anonymous records, for example::

  struct delivery {
	int carrier;

	struct {
		int x;
		int y;
		int z;
	} location;
  };

are valid C, and common, but other languages have no anonymous record types.
Binding generators work around it each in its own way, typically by hoisting
the nested record out under an invented name. **yace** does the same, so that a
header outside the subset can still be used, but reports it: the record should
be defined, named and documented in the header, at the source, rather than
renamed by each generator::

  /**
   * Where a delivery goes
   */
  struct delivery_location {
	int x; ///< And the members...
	int y;
	int z;
  };

  /**
   * A delivery
   */
  struct delivery {
	int carrier;

	struct delivery_location location;
  };

Bit-fields are left out for the same reason: Rust has none, and the packed
structs of Zig are not laid out as C bit-fields are. Use a fixed-width integer
and document the bits, for example with an enum of the masks.

Records cross the boundary by pointer. Passed or returned by value, they depend
on the calling convention of each platform for records, which other languages
implement to varying degrees.

Integers and ``char``
---------------------

The width of ``int``, ``long`` and the others, and whether ``char`` is signed,
are up to the platform. Each target maps them to its language's C types, such
as ``c_int`` and ``c_char`` in Rust, so the bindings have the widths of the
platform, as C does. Where a width matters to the API, say so with the
fixed-width integers.

Functions and enums
-------------------

Do not pass or return an enum. C does not restrict an enum to its values; a
function declared to return ``enum foo_state`` can return any integer, so the
declaration promises a type safety C does not give. Take or return an integer,
and document the enum it takes its values from::

	/**
	 * Upper and lower threshold
	 */
	enum foo_threshold {
		FOO_THRESHOLD_UPPER = 200, ///< Upper limit
		FOO_THRESHOLD_LOWER = 100, ///< Lower limit
	};

The enum names and documents the values, and gives other languages a place to
put them.

Variadic functions are left out: calling them is not portable across
languages. Neither are inline or static functions, which are code, not part of
the boundary, nor variables.

typedef
-------

Only function pointers may be ``typedef``'d::

  typedef int (*binop_func)(int x, int y);

so that functions taking callbacks are readable::

  int
  apply_func(binop_func op, int a, int b);

A function pointer typedef must end in ``_cb``, ``_callback``, ``_fn``,
``_fun``, ``_func`` or ``_function``, as nothing else tells a reader that the
name is a function pointer, and its parameters must be named, as the names, and
their documentation, are what tell a reader how it is called.

Other typedefs only give a type another name. That name hides the type it
stands for, and is not a new type: it gives no more type safety than the type
itself. Refer to types by their own names. Do not name types with the ``_t``
suffix either; it is reserved by POSIX.

Documentation
-------------

Every declaration on the boundary must be documented, with a Doxygen comment
before it, or a ``///<`` after it, so the bindings generated are documented
too. A declaration has one such comment: two adjacent ones would be read as
one, so they are reported.
