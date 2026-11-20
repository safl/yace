.. SPDX-FileCopyrightText: Simon A. F. Lund <os@safl.dk>
..
.. SPDX-License-Identifier: GPL-2.0-only

.. _sec-usage:

=======
 Usage
=======

You describe the FFI boundary of a C API as a C header, in the subset of C99
described in :ref:`sec-ir-csubset`. **yace** parses the header into its
:ref:`sec-ir`, and generates the code of the API for each target language from
the IR.

Command-Line Interface
======================

.. literalinclude:: 050_yace_help.cmd
   :language: bash
   :lines: 1-

.. literalinclude:: 050_yace_help.out
   :language: text
   :lines: 1-

Given C headers, **yace** parses them as one API, see
:ref:`sec-ir-csubset`, writes the IR to ``<prefix>.yaml`` and the diagnostics to
``<prefix>.status``, and prints the diagnostics. The prefix is the one that
``--meta`` gives, or else the name of the first header. A diagnostic is a
place where the header steps outside the C subset. The header is still parsed
and the IR written, but a diagnostic fails the run before any code is
generated. With ``--lenient``, the code is generated anyway, and what the
diagnostics point at will likely not bind well, or at all. A note reports what
is skipped without the header breaking a rule, such as a static inline function;
notes are written to ``<prefix>.status``, and do not fail the run, see
:ref:`sec-ir-rules`.

Given IR files, ``.yaml``, **yace** reads them instead. Either way, ``--emit``
generates the code of the given targets, and checks it, unless ``--no-check``.
A check builds with the toolchain of its target, named by a variable of the
environment where set: ``CC``, ``CXX``, ``CARGO``, ``ZIG`` and ``GO``. A
missing toolchain fails the check, naming the variable.

The emitted code is formatted by the formatter of its language: the Python by
black, the Go by gofmt and its ``go.mod`` by ``go mod edit -fmt``, the Rust by
rustfmt, the Zig by ``zig fmt``, the TOML by taplo, and the C and C++, in every
target, by clang-format in the style of xNVMe, ``src/yace/xnvme.clang-format``.
black, clang-format and taplo are dependencies of **yace**, pinned to one
version each; gofmt, rustfmt and ``zig fmt`` come with the toolchain of their
language, named by ``GOFMT``, ``RUSTFMT``, ``GO`` and ``ZIG`` where set.
Cython has no formatter, so the ``.pyx`` and ``.pxd`` files of the Cython
target keep the layout **yace** writes. The Rust target also writes the
``rustfmt.toml`` it is formatted with. The same headers then give the same
bytes for the same versions of **yace** and of those toolchains. A target whose formatter is missing is not
emitted, also with ``--no-check``, and the run fails naming the formatter.

``--toolchains`` prints, as JSON, the toolchains and the formatters of the
``--emit`` targets, or of every target: each one's command, where it is found,
and its version, so that whoever records a run can record what it was checked
and formatted with.

The IR has no place in a C header for the name, prefix, license and so on of
the API; give those in a YAML file with ``--meta``, of the fields of
:py:class:`yace.ir.model.Meta`.

``errmsg`` in the meta names the function of the API that returns the message
of the call that failed last on the calling thread, a ``const char
*f(void)``, such as ``foo_errmsg``. The C++ and the Python targets then put
that message in the error of a function documented ``@errno``, see
:ref:`sec-targets-cpp` and :ref:`sec-targets-python`. A name that is no such
function is reported by the rule ``meta``. The Rust, Zig and Go targets do not
use ``errmsg``.

A target takes its options as ``--target-option <target>.<key>=<value>``:
``capi_pp.form``, see :ref:`sec-targets-capi`, and ``cpp.std``, see
:ref:`sec-targets-cpp-std`.

Example
=======

The header of the example library, ``examples/libfoo/include/foo.h``:

.. literalinclude:: ../../../examples/libfoo/include/foo.h
   :language: c
   :caption:
   :lines: 1-

Its meta, ``examples/libfoo/meta.yaml``:

.. literalinclude:: ../../../examples/libfoo/meta.yaml
   :language: yaml
   :caption:
   :lines: 1-

Parse it, and generate and check its bindings for every target:

.. literalinclude:: 200_example.cmd
   :language: bash
   :lines: 1-

which writes:

.. literalinclude:: 300_output.out
   :language: text
   :lines: 1-

The C API generated:

.. literalinclude:: ../../../output/capi/libfoo.h
   :language: c
   :caption:
   :lines: 1-
