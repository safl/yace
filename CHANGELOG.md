# Changelog

Each release of yace has a section here, named by its version, such as
`## 0.6.0`. That section is the text of the release on GitHub.

A release is made by merging a pull request whose last commit is
`ver: bump to vX.Y.Z`. That commit sets `__version__` in `src/yace/__init__.py`
and adds the `## X.Y.Z` section to this file. When it lands on `main`,
`.github/workflows/release.yml` checks both, takes the build that the pull
request's checks tested, publishes it to PyPI, tags it, and creates the GitHub
release. Release tags are not pushed by hand.

## Unreleased

The headers given are parsed together, in the order given, after
`<stdbool.h>`, `<stddef.h>` and `<stdint.h>`, and it is that set which has to
compile, not each header alone. A header may use the standard types and what a
header given before it declares without including either, as the parts of a
library read through its umbrella header do. The `self-contained` rule is gone;
a set that does not compile is a `parse-error`, and a type from any other
header is still an `external-type`.

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
