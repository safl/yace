# Changelog

Each release of yace has a section here, named by its version, such as
`## 0.6.0`. That section is the text of the release on GitHub.

A release is made by merging a pull request whose last commit is
`ver: bump to vX.Y.Z`. That commit sets `__version__` in `src/yace/__init__.py`
and adds the `## X.Y.Z` section to this file. When it lands on `main`,
`.github/workflows/release.yml` checks both, takes the build that the pull
request's checks tested, publishes it to PyPI, tags it, and creates the GitHub
release. Release tags are not pushed by hand.

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
