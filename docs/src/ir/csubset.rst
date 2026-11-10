.. SPDX-FileCopyrightText: Simon A. F. Lund <os@safl.dk>
..
.. SPDX-License-Identifier: GPL-2.0-only

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

An API of several headers
-------------------------

A library may describe its API in more than one header, such as an umbrella
header and one header per part of the API. The headers given to **yace** are
the API: it parses them together, as one model, and generates one binding of
it per target. What they declare of each other is internal to the API, and
what any other header declares, those of the system included, is external.

The headers given, in the order given, compile together as one unit; that set,
not each header in it, is what has to be self-contained. **yace** includes
``<stdbool.h>``, ``<stddef.h>`` and ``<stdint.h>`` before them, so a header
may use the standard types those declare without including them, and a header
may use what one given before it declares without including it. The
umbrella header of a library often does this on behalf of its parts, and the
parts can then be given in its order. A set that does not compile, such as
one given in an order where a type is used before the header declaring it, is
reported as ``parse-error``. Of the system headers, only the types listed above
may appear in the API; ``ssize_t``, from ``<sys/types.h>``, is the one a header
includes itself.

A set whose umbrella header includes other system headers on behalf of its
parts, such as ``<stdio.h>``, can be given them with ``--prelude``, once for
each, as ``--prelude stdio.h``. They are included after the standard headers
above and before the set, as the umbrella would, and the IR records them in its
meta, so that the generated C header includes them too. What they declare is
not part of the API: a type of theirs that the API uses, such as ``FILE``, is
still reported as external-type.

For example, of a library whose headers are in ``include/``::

  yace --emit python rust -I include include/libfoo.h include/libfoo_*.h

The IR and the status are named by the first header given, ``libfoo.yaml``
and ``libfoo.status``. A header left out, such as one of internal helpers, is
not part of the API; a type from it is external.

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
and name its parts with masks, as a field of bits, below.

Records cross the boundary by pointer. Passed or returned by value, they depend
on the calling convention of each platform for records, which other languages
implement to varying degrees. How layout and calling conventions bear on a
binding, and what **yace** does with records by value, bit-fields and packed
records, is in :ref:`sec-ir-background`.

Fields of bits
--------------

A field of bits, such as a status of a device, is an unsigned integer of the
width the field has, and each of its parts is named by a mask: an object-like
``#define`` of the part's bits in their place. The integer's doc names the
prefix of its masks, and each mask's doc ends in which bits of which field it
is::

  /**
   * A status
   */
  struct foo_status {
	uint16_t code; ///< Status code, see FOO_STATUS_CODE_*
  };

  /** Generic, command specific or media error; bits 2:0 of 'code' */
  #define FOO_STATUS_CODE_TYPE 0x7
  /** Whether there is more in the log; bit 15 of 'code' */
  #define FOO_STATUS_CODE_MORE 0x8000

The masks are named ``<PREFIX>_<STRUCT>_<FIELD>_<PART>``, and follow the
record, in the order of its fields and of the bits within each. **yace** links
each mask to its field in the IR, as :py:class:`yace.ir.decls.Mask`, and the
targets use it.

The link is declared by the doc comments, not by a tag of yace's own. Both ends
of it are written by the author of the header, the field naming the prefix of
its masks and each mask naming its field and its bits, so nothing is inferred
from a name alone, and the convention is the one a header for C would follow
anyway, as xNVMe's do. A tag would say again what the two comments already say.
What remains is to check that they agree, and every way they may not is
reported by the bit-mask rule, the mask left unlinked: a mask whose name is
under the prefix of no field of that name, or of more than one; a prefix that
does not end in the field's name; a field that is not an unsigned integer; a
mask of no bits, of bits that are not contiguous, or wider than the field; a
doc whose bits are not those of the value; masks of a field that overlap; a
part that is no identifier, or whose accessor, ``<field>_<part>``, the record
has already; and a ``#define`` under the prefix of a field of bits whose doc
does not say which bits it is. A field whose ``see <PREFIX>_*`` names constants
none of which say which bits they are, such as the values of an opcode, is not
a field of bits.

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
languages, see :ref:`sec-ir-background`. Neither are inline or static
functions, which are code, not part of the boundary, nor variables.

typedef
-------

Only function pointers may be ``typedef``'d::

  typedef int (*binop_func)(void *ctx, int x, int y);

so that functions taking callbacks are readable::

  /**
   * Apply 'op' to 'a' and 'b'
   *
   * @lifetime op call
   */
  int
  apply_func(binop_func op, void *ctx, int a, int b);

A function pointer typedef must end in ``_cb``, ``_callback``, ``_fn``,
``_fun``, ``_func`` or ``_function``, as nothing else tells a reader that the
name is a function pointer, and its parameters must be named, as the names, and
their documentation, are what tell a reader how it is called.

Other typedefs only give a type another name. That name hides the type it
stands for, and is not a new type: it gives no more type safety than the type
itself. Refer to types by their own names. Do not name types with the ``_t``
suffix either; it is reserved by POSIX.

What C cannot say
-----------------

C declares types, not intent. ``int foo_open(const char *name, struct foo_handle
**handle)`` does not say that ``handle`` is written rather than read, that the
handle must later be given to ``foo_close()``, or that a negative return is an
errno. A binding that only calls C needs none of this; one that is idiomatic in
its language needs all of it: to return what is written, to raise or return an
error, and to release the handle when it goes out of scope.

Two rules settle what a convention can:

* A returned string is ``const char *``, and borrowed: it belongs to the
  library, or to the handle it came from, and is never the caller's to free.
* A callback takes exactly one ``void *``, its context, and a function taking a
  callback takes its context as the next parameter, so that other languages can
  pass a closure.

The rest is said in the Doxygen comment of the function:

``@param[in]``, ``@param[out]``, ``@param[in,out]``
  Doxygen's own: whether the function reads what a pointer points to, writes
  it, or both. Without one, it is read.

``@nullable name ...``
  The named pointers may be NULL; ``return`` names what the function returns.
  Every other pointer must not be.

``@len pointer count ...``
  ``count`` is the number of elements ``pointer`` points to; in pairs.

``@errno``
  The function returns a negative errno on failure, and zero or more on
  success.

``@destroys name``
  The function releases the handle given as ``name``, its only parameter. An
  opaque record that a function creates through an ``[out]`` pointer must have a
  function that destroys it.

``@lifetime callback call|once|handle ...``
  How long the library may invoke the callback; pairs, one for every callback
  parameter. ``call``: only during the call, as a visitor. ``once``: at most
  once, after the call has returned, and not at all when it fails, as the
  completion of a command submitted, invoked from a later call such as a poll.
  ``handle``: any number of times, until the handle the function is a method of
  is destroyed, and not at all when the call fails, as a handler registered;
  the function's first parameter is then a pointer to an opaque record the
  header declares. In every case the library invokes it on the thread that
  called into the library. The ``void *`` after the callback, its context, has
  no ``@len``.

  Nothing in C says which, and yace cannot tell, so ``@lifetime`` is a promise
  the author of the header makes: the bindings keep the closure, and its
  context, exactly as long as it says. A ``once`` callback the library never
  invokes, as when its handle is destroyed first, is leaked rather than freed,
  as nothing tells the bindings that it never will be. A callback without a
  ``@lifetime`` breaks the callback-lifetime rule, and is bound only as a raw
  function pointer.

  The example library has one of each: ``foo_point_visit()`` takes a ``call``
  callback, ``foo_count_submit()`` a ``once`` callback, which
  ``foo_count_complete()`` invokes, and ``foo_point_watch()`` a ``handle``
  callback, invoked for each point added until the handle is closed. Every
  target's check uses all three.

For example::

  /**
   * Open a handle holding no points
   *
   * @param[in] name Name of the handle, copied
   * @param[out] handle Set to the handle opened
   *
   * @return 0 on success, -EINVAL when 'name' or 'handle' is NULL
   *
   * @errno
   */
  int
  foo_open(const char *name, struct foo_handle **handle);

  /**
   * Close a handle
   *
   * @param handle The handle to close, NULL is ignored
   *
   * @nullable handle
   * @destroys handle
   */
  void
  foo_close(struct foo_handle *handle);

Every tag is checked: one naming a parameter that does not exist, or one that
does not fit it, such as ``@errno`` on a function returning a pointer, is
reported by the annotation rule. What the tags say is recorded in the IR, on
the function and its parameters; see :py:mod:`yace.ir.semantics`.

Documentation
-------------

Every declaration on the boundary must be documented, with a Doxygen comment
before it, or a ``///<`` after it, so the bindings generated are documented
too. A declaration has one such comment: two adjacent ones would be read as
one, so they are reported.
