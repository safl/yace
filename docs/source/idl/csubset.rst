.. _sec-idl-csubset:

The C Subset
============

**Yace** supports **C99** data types (``bool``, ``signed`` / ``unsigned char``,
``intX_t``, ``uintX_t``, etc.), derived types (``enum``, ``struct``, ``union``),
declarations of functions and function points, pointers, arrays, and ``#define
NAME <literal>``.

As you might have noticed, then this means that **Yace** intends to only parse
headers or in other words the entities that usually go into headers.

 won't be able to parse
e.g. a **header-only-library** since these tend to embed logic into functions
declared inline. For sufficiently simple function-bodies, these could be
translated into equivalent 

First, header-libraries are unsupported, that since, they are basically C code
inlined in the header-file which requires compilation. Since, code that needs
compilation is rarely usable on a FFI boundary, unless using something like Zig.
Thus, logic should be implemented in a library, and in the header / FFI / IDL,
one defines the functional declaration to call to execute that logic.

However, using these have contraints when considering portable code and code
that you want to work predictably accross a FFI.

Most of the scalar / pod data types of C are either platform, system dependent
or implementation specific in terms of singedness and width. For example, the
data type ``int`` has platform dependent width, one might be accustomed to
``int`` being 32 bits wide, when working on popular 32bit and 64bit x86 and
ARM systems. However, the C standard does not guarantee this size. It can be as
little as 16bit and even more than 64 bits on some systems.

To reduce this then **Yace** currently experiments with:

* When parsing a C header, then UnsupportedType errors are emitted to let you
  know that these types are being coerced into fixed-width / portable types.

* A callable helper-function (TODO) is emitted that checks the width and signage

  - In case of type-coercsion, then this function can inform at runtime what
    is affected

The reasoning behind this is that FFIs will do this on your behalf anyway.

Making an active decision ahead-of-time, instead of being subjected to multiple
different ways of handling variable width and signage, then write your C APIs
with portability in mind, both for running your C library on multiple platforms,
but also for FFI interoperability.

typedef
-------

The C language construct ``typedef`` is severely restricted in **Yace** as it
only supports typedefs of function-pointers. That is, typedefs on the form::

  typedef int (*binop_func)(int, int);

For such a ``typedef``, then ``binop_func`` can then be utilized as a
type-specifier instead of writing the entire function-signature. This makes
C code a lot more readable in function declarations/protoypes such as the
following::

  int
  apply(binop_func op, int a, int b);

Which is significantly nicer to read in **APIs** using callback-functions. This
is an excellent use of the ``typedef`` language construct, it is also the only
one supported by **yace**.

Many C APIs utilize ``typedef`` for various purposes. However, the author
of **Yace** holds the opinion that any use of ``typedef`` beyond what was
described above should be considered harmful. This is because ``typedef`` does
not introduce a new type; it merely provides a new name for an existing type.
This can obscure type information by hiding it behind an arbitrary label, which
arguably makes the code harder to read due to the introduction of unnecessary
indirection.

``char``
--------

The ``char`` is by many compilers treated as signed, however, it is a choice
left to the compiler. This can be troublesome in FFI / portability scenarious.
Thus, to reduce this, then whenever ``char`` is encountered, without explicit
sign qualification, then **yace** will treat is as ``signed char``.

Functions
---------

Are not allowed to return or pass:

* struct or union; by value
* enum

  - Having a function return an enum gives a false sense of type-safety since
    enums in C are not strongly typed. One might think that when a function
    returns an enum, then it can only ever return any of the values defined
    in the given enum. However, this is a fallacy. 	The function can return any
    value, also one which is not a member of the enum. This is a common source
    of errors, and thus not allowed in **Yace**.
  - Similarly, functions should not take enum as input for the same reason.

Datastructures
==============

...

Structs
-------

Structs are the essential type for user-defined data structures. Most data
exchange is somehow encapsulated by a struct. Now, this is excellent, however,
there are a lot of ways of defining structures in C, which do not work well on a
FFI boundary.

One example of this is anonymous nested records, such as::

  struct delivery {
	int carrier;

	struct {
		int x;
		int y;
		int z;
	} location;
  };

This is valid C, and often seen in systems with large structures where
the anonymous structs provide organization. However, such nested anonymous
structures are not supported in languages such as Rust. Thus, what binding
generators often do, is they **hoist** the nested definitions out and re-write
on the form:

	struct delivery_anon_x {
		int x;
		int y;
		int z;
	};

	struct delivery {
		int carrier;

		struct delivery_anon_x location;
	};

Other binding generators choose different strategies. The point here is that
there are many ways structs can be defined, however, only a subset of these
translate into nice bindings. Also, to avoid non-nice names such as injected
"anon" etc. then **yace** will simply not allow these and will error out.

It is then the responsibility of the user to re-write / manually hoist this, in
the C API, into something useful like::

    /**
	 * Describe this...
	 */
	struct delivery_location {
		int x; ///< And the members...
		int y;
		int z;
	};

    /**
	 * Describe this
	 */
	struct delivery {
		int carrier;

		struct delivery_location location;
	};

The reasoning here is that, intead of individual binding-generators applying
different "hoisting" techniques, then rewrite the representation at the
"source". When doing so, it might be that an even better representation could
be achieved.

Union
-----

Enum
----

Enums are great for grouping collections of values and enables a way to refer
to these symbolically and thereby avoid "hardcoding" magic values. Also, unlike
macros such as::

	#define FOO_THRESHOLD_UPPER 200
	#define F00_THRESHOLD_LOWER 100

Then this can be done using an enum like::

	/**
	 * Upper and lower threshold
	 */
	enum foo_threshold {
		FOO_THRESHOLD_UPPER = 200, ///< Upper limit
		FOO_THRESHOLD_LOWER = 100, ///< Lower limit
	};

By doing so, then the "magic" values can be referred to symbolically, just like
the define, however, the values can be documented, and grouped. However, refrain
from using the enum as function return or parameter types. Since C is not
strongly typed, then there is no enforcement that a function returning an enum,
actually returns either 100 or 200 as the enum values above. The funtion could
perfectly well return any other value such as 2.

Thus, only use enums as a way to document and symbolically refer to values.
Having a library / FFI that documents the "magic-values" and provides symbolic
references to them is really useful.
