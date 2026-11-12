<!--
SPDX-FileCopyrightText: Simon A. F. Lund <os@safl.dk>

SPDX-License-Identifier: GPL-2.0-only
-->

# Changelog

Each release of yace has a section here, named by its version, such as
`## 0.6.0`. That section is the text of the release on GitHub.

A release is made by merging a pull request whose last commit is
`ver: bump to vX.Y.Z`. That commit sets `__version__` in `src/yace/__init__.py`
and adds the `## X.Y.Z` section to this file. When it lands on `main`,
`.github/workflows/release.yml` checks both, takes the build that the pull
request's checks tested, publishes it to PyPI, tags it, and creates the GitHub
release. Release tags are not pushed by hand.

## 0.9.6

`--target-option TARGET.KEY=VALUE` passes an option to a target, as
`--generator-option` does to a generator. yace reports an option that the
target does not take, a value that the option does not accept, and an option
of a target not given to `--emit`, before it parses a header.

The `capi_pp` target takes the option `form`. `form=library`, the default,
emits the printers as before. `form=header` defines the printers and the
`_str()` functions as `static inline` in `lib<prefix>_pp.h`, and the helpers as
`static`, and emits no `<prefix>_pp.c`. An optimizing build then compiles only
the printers that a file calls. The helpers are under the include guard
`YACE_PP_HELPERS`, so one file can include the printer headers of several
runs, each with its own prefix.

The documentation has a contributor guide.

## 0.9.5

A function whose doc comment carries `@nobind` is left out of every binding.
The parser drops it before reading its types, so a type outside the C subset,
such as the `FILE *` of a printer, reports nothing, and a static or inline
function is not reported as one. An API can then keep its own printers beside
the types they print rather than in a header left out of the bindings.

The printers of the C target, in `capi` and `capi_pp`, no longer pass the NULL
key of a list element to a `%s`. gcc at `-O2` warned of it where a record
appears only as an array element, which fails a build with `-Werror`. The
checks of both targets now compile at `-O2`, where such warnings show.

## 0.9.4

The new target `capi_pp` generates the pretty-printers of the C target for an
API to compile into its own library. It writes `lib<prefix>_pp.h`, which
declares the printers and includes the API's own headers rather than the
generated `lib<prefix>.h`, and `<prefix>_pp.c`. Its check compiles both, with
the layout assertions, against the API's headers. xNVMe uses it to generate
`libxnvme_pp.h` and `xnvme_pp.c`.

The printers take `<PREFIX>_PR_TERSE` at 0x2, as xNVMe's do, and print YAML for
it. `<PREFIX>_PR_JSON` moves from 0x2 to 0x4 in every target, so a caller that
passes the value 2 rather than the name now gets YAML. In the C target, the
enum of these flags is now `enum <prefix>_pr`, as an API names it, rather than
with the prefix in upper case.

## 0.9.3

The pretty-printers of the C target are smaller. Each record has one function
for both formats, and it prints each field by a call to a helper for the
field's kind, such as `yace_pp_int()`. Before, each record had a function for
JSON and one for YAML, with several `fprintf()` calls for every field. On the
107 records of xNVMe's headers, the printers compile to 92 KB with gcc at -O2,
down from 234 KB. The printed text is unchanged.

A raw call in Python costs less. Where a function has no `const char *`
parameter, the module calls the ctypes function itself once the library is
loaded, rather than a Python wrapper around it. A returned string is still
decoded, and a NULL pointer is still `None`. The ctypes function keeps the
docstring, and `inspect.signature()` still shows its parameters. The arguments
of these functions are now passed by position only.

yace names the IR and the status file by the prefix that the meta gives.
Before, yace named them after the first header, such as
`libxnvme_util.yaml` for all of xNVMe's headers.

## 0.9.2

Every binding now documents a function by the parameters that its caller
passes. For a function documented with `@errno`, each binding shows the C
`@return` text where it documents errors, because the binding returns the value
and reports a failure as an error. Before, the bindings showed that text as the
return value. Every target now carries `@note`, `@see` and `@deprecated`.

In Python, a record field named as a keyword, such as `async`, is reached as a
property with a trailing underscore, `async_`. Before, assigning `async_` set a
new attribute that the C library never saw.

yace stops with an error when it cannot find a header that it includes itself,
such as `stdbool.h`. Before, yace reported the missing header and generated
bindings with wrong layouts. When no clang is installed, yace now uses gcc's
headers.

yace skips a declaration of the headers that has the name of a printer that
yace generates, such as `enum <prefix>_pr`, `<PREFIX>_PR_JSON`, `<record>_pr` or
`<enum>_str`, and reports it with the rule `printer-name`. Before, an API with
printers of its own, such as xNVMe with `libxnvme_pp.h`, gave a Rust crate and a
C API that did not compile.

The field `crate` in the meta names the Rust crate, such as `xnvme-sys`. The
Rust bindings are in `bindings.rs`, which `lib.rs` includes, so another crate
can include them with `include!()`.

## 0.9.1

A function returning a pointer to a record without `const`, an object the
caller may write and give back by its address, such as a command context taken
from a queue's pool, is bound as returning that pointer in every target. It was
bound as returning a copy, so handing it back gave the library the caller's
copy in place of its own, and a NULL return was dereferenced. A `const` pointer
to a record is a view, and is still returned as a copy.

In Rust, a `once` closure given to a function that is not a method of a handle
must be `Send`, as any later call into the library, from any thread, may run
it; one holding an `Rc` raced with its own thread. The closure given to a
method runs during a later call given its handle, which stays on its thread,
and need not be `Send`.

The callback lifetimes have a page of their own in the documentation, and every
file states its copyright and license, as the REUSE specification lays out.

## 0.9.0

Go is a target. Its bindings call the C API through cgo: a raw layer declares
each record as a Go struct of the C layout, a union as its bytes read and
written through a method per member, and each function as a Go function
calling it, and the check does not compile unless the layout is the IR's. The
idiomatic layer over it has handles as structs with their methods and a
destructor to defer, errors returned last as a `syscall.Errno`, results
returned, slices and strings, and a Go function as a callback, kept as its
`@lifetime` says; records print without the C printers.

The Python target also emits `<prefix>.pxd`, the `cdef extern` declarations of
the C API, for Cython code to `cimport` and call in its own loops; its check
compiles a `.pyx` against it where Cython is installed. A record repr's as its
constructor is called, Rust records are `Debug` by their C fields, and C++
prints records and names enums, none of them through the C printers.

A record declared `__attribute__((packed))` is bound packed in every target,
where it was declared unpacked and read the wrong bytes: C and C++ keep the
attribute, Python sets `_pack_`, Rust uses `repr(C, packed)`, Zig aligns each
field to 1, and Go keeps the bytes behind a getter and setter per field.

The checks cover the functions, not only the records. The C target compiles an
assertion per function that the IR's type of it is the header's, which covers
C++, Go and the `.pxd` too, and the Zig target compares its extern functions
with Zig's own import of the headers. `--toolchains` prints what each target's
check builds with, its command, path and version, for a run to record.

A generator writes headers for yace to take as headers written by hand: found
by the `yace.generators` entry point group, or named by its file or module and
class, as `--generate toolbox/spec.py:SpecHeaders`, so a project that is no
Python package needs nothing installed. What it writes is parsed, emitted and
checked under the same rules, its options given as
`--generator-option <name>.<key>=<value>`.

What uses a `volatile` type, or an enum defined nowhere, is skipped and
reported rather than emitted wrong, and a record with a flexible array member
where ISO C allows none is reported.

## 0.8.0

The headers given are the API, parsed together into one IR in the order given,
after `<stdbool.h>`, `<stddef.h>` and `<stdint.h>`. A library read through an
umbrella header, with one header per part and types crossing between them, such
as xNVMe, is described by all of its headers at once: a header may use the
standard types and what a header given before it declares without including
either, and it is the set which has to compile. A set that does not compile is
a `parse-error`, and a type from any other header is an `external-type`.

`--prelude HEADER` includes a system header, such as `stdio.h`, ahead of the
headers, for a set whose umbrella header includes it on behalf of its parts.
The IR records the prelude, and the generated C header includes it; what the
API uses of it is still an `external-type`.

A set that does not compile reports every error, once each, rather than the
first 20 that clang stops at, which hid how far a set was from compiling.

A field of bits, an unsigned integer whose parts are named by `#define` masks,
is linked to its masks in the IR. The integer's doc names the prefix of its
masks, `see FOO_STATUS_CODE_*`, and each mask's doc says which bits of which
field it is, `bits 2:0 of 'code'`. Every way the two can disagree is reported
by the new bit-mask rule, and the mask is left unlinked.

The pretty-printers of every target print a field of bits as its value and its
parts, `code: {val: 0x8a05, type: 0x5, dnr: 0x1}` in YAML, the same in decimal
in JSON. In Python, each part is a property of the record, `status.code_type`;
in Rust, a getter and a setter, `code_type()` and `set_code_type()`; in C++,
functions overloaded on the record, `foo::code_type(status)` and
`foo::set_code_type(status, value)`; in Zig, `codeType()` and `setCodeType()`,
of an integer as wide as the part. The libfoo fixture has a field of bits, and
the check of every target reads, writes and prints its parts.

Breaking: the IR's meta records the headers given, in place of the one header.

## 0.7.0

The header is the description of an FFI boundary, in a C subset. yace reports
every step outside the subset as a diagnostic naming the rule, and skips what
no binding can hold, with everything that uses it, rather than dropping or
coercing it silently. The IR records the layout of each record, and every
target checks it. Doxygen tags say what C cannot: `@param[in|out|in,out]`,
`@nullable`, `@len`, `@errno`, `@destroys`, and `@lifetime` for how long the
library may invoke a callback.

The targets are the C API with pretty-printers, Python through ctypes, a `-sys`
style Rust crate, a header-only C++ layer, and Zig 0.16. Over the raw bindings,
the Python, Rust, C++ and Zig targets add an idiomatic layer: handles released
by their destructors, errors from errno, sequences for arrays, and closures for
callbacks. Every target is checked against the libfoo fixture.

Breaking: the IR format; the CLI, with `--meta`, `--strict`, `--schema` and
`-I`, and `--emit` no longer defaulting to `capi`; and the ctypes target, which
emitted empty modules, is gone.

`make devenv-run` runs a command in the development environment that CI uses.

## 0.6.0

The C parser carries the signature of a function pointer wherever it appears
as a type, such as a struct field or a function parameter, rather than an
opaque pointer. Macros whose value is an expression, such as `(1 << 3)`, or
an alias of another macro, are evaluated by clang and become defines. `size_t`
and `ssize_t` keep their typedef names. A construct the parser cannot handle is
reported as an error rather than stopping it on an assertion.

The capi target emits only what can cross a language boundary. It leaves out
anonymous enums, functions with an undefined type or returning a function
pointer, structs with a by-value field of incomplete type, and redeclarations
of standard library types. What it emits is in dependency order. The check
stage now compiles and runs the generated check program.

`make install` installs the wheel built by `make build`; the editable install
is `make install-source`. Releases are made by CI, as described above.
