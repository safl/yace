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

## 0.13.0

The C++ target generates its layer for C++17 as well as for C++20, chosen
with `--target-option cpp.std=c++17`; C++20 remains the default. The layer for
C++17 declares a class `detail::span` and names it where the layer for C++20
names `std::span`, which is all the layer takes from C++20. `detail::span`
converts from a `std::vector`, a `std::array`, a C array and a pointer with a
length in braces, as `std::span` does, so a call compiles against both layers.
The check is built as the standard the layer is generated for.

The meta takes `errmsg`, the name of the function of the API that returns the
message of the call that failed last on the calling thread, a
`const char *f(void)`. Where it is set, the C++ layer throws
`detail::failure`, a `std::system_error` whose `what()` is the function and
that message, without the text of the errno that `std::system_error` appends,
and the `OSError` of the Python layer has the message as its `strerror`. The
errno is the code as before. The layer reads the message before it destroys
the callable of a callback that the failed call was given. A name that is no such function is reported by
the new rule `meta`, and fails the run. The Rust, Zig and Go targets do not
use `errmsg`.

The fixture library, `examples/libfoo`, keeps a message for each failure and
declares `foo_errmsg()`, which its meta names.

`@arrparam` documents an array in place of `@param`. Its length is the
unsigned integer `<name>_len`, the capacity of an `[out]` array, and an
`[out]` array may have a count written, the `[out]` pointer to an unsigned
integer `<name>_nwritten`, to which the bindings cut the array. `@recparam`
documents a record of arguments, a pointer to a const struct whose size is the
`size_t` `<name>_nbytes`; the function's name ends in `_sized`, the headers
define a static inline function of the name without the suffix, and the
bindings take that name and pass the size of the record's type. The C API
header defines that static inline function too. Where a header names a
parameter otherwise, `@len_at{}`, `@nwritten_at{}` and `@nbytes_at{}` in the
text name it. `@len` is removed, and a header using it is reported by the rule
`annotation`; a signed length or count written, accepted before, is reported
too.

An `[out]` pointer to `void` without a length is reported by the rule
`annotation` and bound as a pointer the function reads. The C++ layer declared
a local of type `void` for it, which did not compile.

The diagnostic of a `#define` without a doc names the file and the line of the
`#define`; it was reported at `<header>`.

In the C++ layer, the comment of a method that destroys a handle and is
documented `@errno` says what the method throws; the `@throws` was left out.

In the C++ layer, a constructor whose name without the handle's is a keyword
keeps the name of the handle: `foo_req_new()` is `foo::req_new()`, and was
`foo::new_()`.

In the C++ layer, a handle given as an argument is a reference to `const`
only where the C parameter points to const; it was always one. A caller that
passed a `const` handle or a temporary to a function whose C parameter is not
a pointer to const no longer compiles.

In the C++ layer, the comment of a function whose text names a parameter that
the signature folds into a span, or returns, has a `@note` saying what the
signature has for the parameter.

## 0.12.0

In the Rust target, a member of a union reads without `unsafe` where that is
sound. Where every member of a union is as large as the union and has no
padding, every byte of the union is initialised however it was written, and
each member of a type for which every bit pattern is a value, such as an
integer, a float, a raw pointer, an enum, or an array or record of those, has
a safe getter of its name, `value.u()`. A `bool` or a function pointer keeps
the unsafe read. The crate asserts the sizes this relies on when it is
compiled.

## 0.11.0

This release changes the layout of the code yace emits, and yace now needs a
formatter for every target it emits.

yace formats what it emits with the formatter of each language: black for the
Python, gofmt for the Go and `go mod edit -fmt` for its `go.mod`, rustfmt for
the Rust, `zig fmt` for the Zig, taplo for the TOML, and clang-format in the
style of xNVMe for the C and C++ of every target. black 26.10.1, clang-format
23.1.3 and taplo 0.9.3 are dependencies of yace, pinned to those versions.
gofmt, rustfmt and `zig fmt` come with the toolchains of their languages,
named by `GOFMT`, `RUSTFMT`, `GO` and `ZIG` where set. A target whose formatter
is missing emits nothing and fails the run, also with `--no-check`. The Rust
target also writes the `rustfmt.toml` it is formatted with, and
`--toolchains` lists the formatters with the toolchains. Cython has no
formatter, so the `.pyx` and `.pxd` files keep the layout yace writes.

The comments and docstrings that every target emits are rewritten where they
were garbled, ambiguous or wrong, and the diagnostics name their subject where
"it" was ambiguous.

The benchmark, `examples/libfoo/bench`, builds every program and libfoo at
optimisation level 3 for the baseline CPU. `bench.cpu` pins every program to
one core, and `bench.khz` pins that core's clock through cpufreq. Each
program's rounds are calibrated so that a run of its slowest way takes
`bench.seconds`, and the report gives how busy each CPU was and the core's
clock while each program ran.

## 0.10.0

This release breaks the command line and the Rust and C++ bindings.

A diagnostic now fails the run, and no code is generated, unless `--lenient`
is given; `--strict` is removed. What only the C compiler uses, a static
assert, a static or inline function and a function-like macro, is reported as
a note, which does not fail the run. The status line counts the notes, and
`-l` lists them.

In the Rust and C++ idiomatic layers, an `[out]` array is a buffer that the
caller gives, `&mut [T]` and `std::span<T>`, as in Go and Zig. Its length is
the capacity, which is no longer a parameter, and the function returns the
part written, so nothing is allocated. Python allocates the array, as before.

A second `@len` on an `[out]` array may name an `[out]` pointer to an
integer, the number of elements written; the bindings return that many.
`@errno partial` states that a function writes its outputs also when it
fails, and the error of every target then carries them: `OSError.partial` in
Python, `Partial<T>` in Rust, `partial_error<T>` in C++, the values returned
with the error in Go, and a `partial` parameter in Zig.

The parser handles `#pragma pack`. It skips, with a diagnostic, a function
whose calling convention is not that of C, such as `ms_abi`, and a record
whose layout an aligned attribute changes. It leaves out an enumerator that
does not fit an `int`, and leaves out an enum when all of its enumerators are
left out. It reports an attribute on a field.

The Zig check asserts the size and alignment of a record of bit-fields. The Go
target no longer creates an empty directory for the C target. Each item of a
Doxygen list in a description keeps a line of its own in the documentation of
every target.

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
key of a list element to a `%s`. gcc at `-O2` warned about the NULL argument
where a record appears only as an array element, which fails a build with
`-Werror`. The
checks of both targets now compile at `-O2`, where such warnings show.

## 0.9.4

The new target `capi_pp` generates the pretty-printers of the C target for an
API to compile into its own library. It writes `lib<prefix>_pp.h`, which
declares the printers and includes the API's own headers rather than the
generated `lib<prefix>.h`, and `<prefix>_pp.c`. Its check compiles both, with
the layout assertions, against the API's headers. xNVMe uses it to generate
`libxnvme_pp.h` and `xnvme_pp.c`.

The printers take the flag `<PREFIX>_PR_TERSE`, with the value 0x2 as in
xNVMe, and print YAML for it. `<PREFIX>_PR_JSON` moves from 0x2 to 0x4 in every
target, so a caller that passes the value 2 rather than the name now gets YAML.
In the C target, the enum of these flags is now named `enum <prefix>_pr`, in
lower case as C APIs name enums. Before, the prefix was in upper case.

## 0.9.3

The pretty-printers of the C target are smaller. Each record has one function
for both formats, and it prints each field by a call to a helper for the
field's kind, such as `yace_pp_int()`. Before, each record had a function for
JSON and one for YAML, with several `fprintf()` calls for every field. On the
107 records of xNVMe's headers, the printers compile to 92 KB with gcc at -O2,
down from 234 KB. The printed text is unchanged.

In Python, a raw call to a function without a `const char *` parameter calls
the ctypes function directly once the library is loaded, rather than through a
Python wrapper around the ctypes function. A returned string is still
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
the closure. Before, a closure holding an `Rc` could run on another thread than
the other owners of the `Rc`. A closure given to a method runs during a later
call on the same handle, and the handle stays on its thread, so that closure
need not be `Send`.

The callback lifetimes have a page of their own in the documentation, and every
file states its copyright and license, as the REUSE specification lays out.

## 0.9.0

Go is a target. Its bindings call the C API through cgo. The raw layer
declares each record as a Go struct with the C layout, each union as its bytes,
read and written through a method per member, and each C function as a Go
function that calls it. The check does not compile unless the layout is the one
in the IR. In the idiomatic layer, a handle is a struct with methods and a
destructor to call with `defer`, an error is returned last as a
`syscall.Errno`, results are returned, an array is a slice, a C string is a Go
string, and a callback is a Go function, kept as long as its `@lifetime` says.
Records print without the C printers.

The Python target also emits `<prefix>.pxd`, the `cdef extern` declarations of
the C API, for Cython code to `cimport` and call in its own loops; its check
compiles a `.pyx` against it where Cython is installed. The `repr()` of a
Python record is written as a call of its constructor, Rust records implement
`Debug` by their C fields, and C++ prints records and the names of enum values.
None of these use the C printers.

A record declared `__attribute__((packed))` is bound packed in every target,
where it was declared unpacked and read the wrong bytes: C and C++ keep the
attribute, Python sets `_pack_`, Rust uses `repr(C, packed)`, Zig aligns each
field to 1, and Go keeps the bytes behind a getter and setter per field.

The checks cover the functions, not only the records. The C target compiles an
assertion per function that the IR's type of it is the header's, which covers
C++, Go and the `.pxd` too, and the Zig target compares its extern functions
with Zig's own import of the headers. `--toolchains` prints what each target's
check builds with, its command, path and version, for a run to record.

A generator writes headers that yace takes as if they were written by hand.
yace finds a generator by the `yace.generators` entry point group, or by its
file or module and class, as in `--generate toolbox/spec.py:SpecHeaders`, so a
project that is not a Python package needs nothing installed. The headers a
generator writes are parsed, emitted and checked under the same rules as other
headers. Its options are given as `--generator-option <name>.<key>=<value>`.

A declaration that uses a `volatile` type, or an enum that is not defined, is
skipped and reported; before, it was emitted wrong. A record with a flexible
array member where ISO C allows none is reported.

## 0.8.0

The headers given are the API, parsed together into one IR in the order given,
after `<stdbool.h>`, `<stddef.h>` and `<stdint.h>`. A library read through an
umbrella header, with one header per part and types crossing between them, such
as xNVMe, is described by all of its headers at once. A header may use the
standard types, and what a header given before it declares, without including
either. The set of headers has to compile, not each header alone. A set that
does not compile is a `parse-error`, and a type from any other header is an
`external-type`.

`--prelude HEADER` includes a system header, such as `stdio.h`, ahead of the
headers, for a set whose umbrella header includes it on behalf of its parts.
The IR records the prelude, and the generated C header includes it; what the
API uses of it is still an `external-type`.

For a set that does not compile, yace reports every error, once each, rather
than the first 20, after which clang stops.

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

This release breaks the IR: its meta records the headers given, in place of
the one header.

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

This release breaks the IR format and the CLI. The CLI has `--meta`,
`--strict`, `--schema` and `-I`, and `--emit` no longer defaults to `capi`. The
ctypes target, which emitted empty modules, is removed.

`make devenv-run` runs a command in the development environment that CI uses.

## 0.6.0

The C parser carries the signature of a function pointer wherever it appears
as a type, such as a struct field or a function parameter, rather than an
opaque pointer. Macros whose value is an expression, such as `(1 << 3)`, or
an alias of another macro, are evaluated by clang and become defines. `size_t`
and `ssize_t` keep their typedef names. The parser reports a construct that it
cannot handle as an error, rather than stopping on an assertion.

The capi target emits only what can cross a language boundary. It leaves out
anonymous enums, functions with an undefined type or returning a function
pointer, structs with a by-value field of incomplete type, and redeclarations
of standard library types. What it emits is in dependency order. The check
stage now compiles and runs the generated check program.

`make install` installs the wheel built by `make build`; the editable install
is `make install-source`. Releases are made by CI, as described above.
