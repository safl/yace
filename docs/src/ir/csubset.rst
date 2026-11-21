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

Without ``--meta``, the IR and the status are named by the first header given,
``libfoo.yaml`` and ``libfoo.status``. With a meta that gives the prefix
``foo``, they are ``foo.yaml`` and ``foo.status``. A header left out, such as
one of internal helpers, is not part of the API; a type from it is external.

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

Variadic functions are outside the subset: calling them is not portable across
languages, see :ref:`sec-ir-background`. A variadic function is reported, and
recorded in the IR as ``variadic``. The C API, the Cython ``.pxd`` of the
Python target, and the raw layers of Rust and Zig declare it. The Python module
and the Go package do not bind it, and no idiomatic layer wraps it.

Inline and static functions, function-like macros and static assertions are
used by the C compiler only, and are not part of the boundary. They are skipped
and reported as notes, which do not fail the run. Variables are skipped too,
and reported as diagnostics, since a variable has a symbol that other languages
cannot bind. None of them is in the IR.

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

Three rules settle what a convention can settle:

* A returned string is ``const char *``, and borrowed: it belongs to the
  library, or to the handle it came from, and is never the caller's to free.
* A returned ``const`` pointer to a record is a view: bindings may hand back a
  copy. Without ``const`` it is an object the caller may write, and given to
  other functions by its address, so bindings return the pointer.
* A callback takes exactly one ``void *``, its context, and a function taking a
  callback takes its context as the next parameter, so that other languages can
  pass a closure.

The rest is said in the Doxygen comment of the function:

``@param[in]``, ``@param[out]``, ``@param[in,out]``
  Doxygen's own: whether the function reads what a pointer points to, writes
  it, or both. Without one, it is read.

``@arrparam name text``
  As ``@param``, for an array, with a direction as ``@param`` has. Its length
  is the unsigned integer ``<name>_len``; of an ``[out]`` array, that is the
  capacity, which the caller gives. An ``[out]`` array may also have a count of
  the elements the function wrote, the ``[out]`` pointer to an unsigned integer
  ``<name>_nwritten``; the bindings return the array cut to that count. Where
  a parameter is named otherwise, ``@len_at{length}`` and
  ``@nwritten_at{count}`` in the text name it.

``@recparam name text``
  As ``@param``, for a record of arguments, as the record arguments pattern
  below describes: ``name`` is an ``[in]`` pointer to a const struct, and its
  size is the ``size_t`` ``<name>_nbytes``, or the parameter that
  ``@nbytes_at{size}`` in the text names. The function's name ends in
  ``_sized``, and the headers define a static inline function of the name
  without the suffix, which passes ``sizeof``; yace checks that the function
  exists, not what it passes.

``@nullable name ...``
  The named pointers may be NULL; ``return`` names what the function returns.
  Every other pointer must not be.

``@errno``
  The function returns a negative errno on failure, and zero or more on
  success. ``@errno partial`` says that the function writes its ``[out]``
  parameters also when it fails, so that what it wrote is not lost: the error
  of each binding carries what the call returns when it succeeds. The function
  returns ``int``, since a count it returned would be lost to the errno, and
  has an ``[out]`` parameter, and no ``[out]`` handle, since nobody owns a
  handle from a failed call.

``@destroys name``
  The function releases the handle given as ``name``, its only parameter. An
  opaque record that a function creates through an ``[out]`` pointer must have a
  function that destroys it.

``@lifetime callback call|once|handle ...``
  How long the library may invoke the callback, one for every callback
  parameter: ``call``, only during the call; ``once``, at most once, after it;
  ``handle``, until the handle is destroyed. Nothing in C says which, so it is
  a promise the author of the header makes, and the bindings keep the closure
  exactly as long as it says. A callback without one breaks the
  callback-lifetime rule, and is bound only as a raw function pointer. The
  ``void *`` after the callback, its context, is no ``@arrparam``. See
  :ref:`sec-ir-lifetimes`, which describes each with the example library's
  callbacks.

``@nobind``
  The function is not bound in any language. yace leaves it out before reading
  its types, so they may be outside the subset, such as the ``FILE *`` of a
  printer of the library's own, which C callers use and the bindings replace.
  A static or inline function with the tag is left out without being reported.

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
   * Take the points that are ready, as many as fit
   *
   * @param handle The handle
   * @arrparam[out] points The points taken @len_at{max} @nwritten_at{taken}
   * @param max The number of points that 'points' has room for
   * @param[out] taken Set to the number of points taken, also on failure
   *
   * @return 0 on success, a negative errno on failure
   *
   * @errno partial
   */
  int
  foo_take(struct foo_handle *handle, struct foo_point *points, uint32_t max,
           uint32_t *taken);

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

Named ``points_len`` and ``points_nwritten``, the parameters of ``foo_take()``
would need neither ``@len_at`` nor ``@nwritten_at``. Where a parameter has
the conventional name, a reference naming another is reported, as the name
would mislead. So is a reference outside the text of an ``@arrparam`` or
``@recparam``, one without its parameter in braces, one given twice, and a
parameter documented by ``@arrparam`` or ``@recparam`` and another tag. In the
comment of anything but a function, the references, ``@arrparam`` and
``@recparam`` are reported too.

Doxygen reads ``@arrparam`` and ``@recparam`` as ``@param``, and the
references inline, through aliases::

  ALIASES += arrparam=@param
  ALIASES += recparam=@param
  ALIASES += "len_at{1}=(length: @p \1)"
  ALIASES += "nwritten_at{1}=(count written: @p \1)"
  ALIASES += "nbytes_at{1}=(size: @p \1)"

Every tag is checked: one naming a parameter that does not exist, or one that
does not fit it, such as ``@errno`` on a function returning a pointer, is
reported by the annotation rule. What the tags say is recorded in the IR, on
the function and its parameters; see :py:mod:`yace.ir.semantics`.

Patterns
--------

The rules and tags above describe a function one parameter at a time. Some
functions combine them into a recurring shape, a pattern, which each binding
turns into the idiom of its language. Each pattern is listed with its C shape
and what the bindings make of it.

Handle
  An opaque record, created by a function that writes it through an ``[out]``
  pointer to a pointer, and released by the function that ``@destroys`` it.
  The functions taking it as their first parameter are its methods. The
  bindings make it a type that owns the pointer and releases it when it goes
  out of scope.

Callback and context
  A pointer to a function taking one ``void *``, followed by that ``void *``,
  its context, with a ``@lifetime``. The bindings take a closure, and pass the
  context themselves.

Array and length
  An ``@arrparam``, and its length. An array read is given as a sequence, and
  its length is not given. Of an ``[out]`` array, the length is the capacity,
  and the count written, where there is one, cuts the array the bindings
  return.

Record arguments
  A function taking its arguments as a record, so that arguments can be added
  without changing its signature::

    /**
     * ...
     * @param handle The handle
     * @recparam args The arguments, see ::foo_read_args
     * @param args_nbytes The size of the record the program was built with
     */
    int
    foo_read_sized(struct foo_handle *handle, const struct foo_read_args *args,
                   size_t args_nbytes);

    static inline int
    foo_read(struct foo_handle *handle, const struct foo_read_args *args)
    {
            return foo_read_sized(handle, args, sizeof(*args));
    }

  The library compares ``args_nbytes`` with the size of its own record to tell
  a program built against an older header, whose record is smaller, and reads
  the members that record lacks as zero. So members are only added at the end
  of the record, and zero is the default of every member. C callers call the
  static inline function, which passes the size. The bindings cannot call it,
  so they pass the size of the record's type themselves, and take its name:
  ``handle.read(args)``. A function may take more than one record, each with
  a size of its own, anywhere among its parameters.

Buffer
  Memory for the library's use that the library allocates, by functions named
  for it::

    void *foo_buf_alloc(const struct foo_handle *handle, size_t nbytes);
    void *foo_buf_realloc(const struct foo_handle *handle, void *buf, size_t nbytes);
    void foo_buf_free(const struct foo_handle *handle, void *buf);

  ``<stem>_alloc`` returns a ``void *`` to ``size_t nbytes`` bytes.
  ``<stem>_free`` frees it, taking it as its one ``void *``.
  ``<stem>_realloc``, where there is one, resizes it, taking it and
  ``nbytes``. The other parameters of the two are named and typed as
  parameters of ``<stem>_alloc``, and the bindings pass them the values the
  buffer was allocated with. An allocation without a ``<stem>_free`` breaks
  the buffer-lifecycle rule. The bindings make the buffer a type that owns the
  memory and frees it when it goes out of scope. What ``<stem>_alloc`` writes
  to an ``[out]`` parameter, such as a physical address, is returned with the
  buffer, as for any function. The bindings cannot pass ``<stem>_realloc`` an
  ``[out]`` parameter again, as they have no place to return it, so such a
  buffer cannot be resized, and ``<stem>_realloc`` is left to the raw layer,
  as it frees the memory the buffer owns.

Registration
  Memory of the caller's that the library is to use, such as memory a device
  reads and writes directly, by functions named for it::

    int foo_buf_register(const struct foo_handle *handle, void *vaddr, size_t nbytes);
    int foo_buf_unregister(const struct foo_handle *handle, void *vaddr);

  ``<stem>_register``, documented ``@errno``, registers ``size_t nbytes``
  bytes at its one ``void *``, until ``<stem>_unregister`` takes that address.
  The other parameters of ``<stem>_unregister`` are named and typed as
  parameters of ``<stem>_register``. A registration without an
  ``<stem>_unregister``, or without ``@errno``, breaks the buffer-lifecycle
  rule. The bindings take the memory as an object of their language, keep it
  alive while it is registered, and unregister it when the registration goes
  out of scope.

Documentation
-------------

Every declaration on the boundary must be documented, with a Doxygen comment
before it, or a ``///<`` after it, so the bindings generated are documented
too. A declaration has one such comment: two adjacent ones would be read as
one, so they are reported.

Each binding carries the doc comment into the documentation format of its
language. It carries the brief, the paragraphs after the brief, ``@note``,
``@see`` and ``@deprecated``, the ``@param`` text of each parameter that the
caller passes, and ``@return``. A function documented with ``@errno`` behaves
differently in every binding except the C API: the binding returns the value
and reports a failure as an error. The ``@return`` text of such a function
describes both, and yace cannot separate the two. Each binding therefore shows
that text where it documents errors: under ``# Errors`` in Rust, ``Raises:`` in
Python, ``@throws`` in C++, and ``Errors:`` in Zig and Go. The text starts with
the name of the C function, as in ``foo_open() returns: 0 on success, ...``.
With ``@errno partial``, a sentence follows that says where the error holds
what the call wrote: ``partial`` of the ``OSError`` in Python, ``value`` of
the ``Partial`` error in Rust and of the ``partial_error`` exception in C++,
the values returned with the error in Go, and the trailing ``partial``
parameter in Zig, whose errors carry no value.
