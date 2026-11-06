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
:ref:`sec-ir-csubset`, writes the IR to ``<stem>.yaml`` and the diagnostics to
``<stem>.status``, named by the first header, and prints the diagnostics. A diagnostic is a
place where the header steps outside the C subset; the header is still parsed,
and its code still generated, but what the diagnostics point at will likely not
bind well, or at all. With ``--strict``, any diagnostic is an error.

Given IR files, ``.yaml``, **yace** reads them instead. Either way, ``--emit``
generates the code of the given targets, and checks it, unless ``--no-check``.
A check builds with the toolchain of its target, named by a variable of the
environment where set: ``CC``, ``CXX``, ``CARGO``, ``ZIG`` and ``GO``. A
missing toolchain fails the check, naming the variable.
``--toolchains`` prints, as JSON, the toolchains of the ``--emit`` targets, or
of every target: each one's command, where it is found, and its version, so
that whoever records a run can record what it was checked with.

The IR has no place in a C header for the name, prefix, license and so on of
the API; give those in a YAML file with ``--meta``, of the fields of
:py:class:`yace.ir.model.Meta`.

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

Parse it, strictly, and generate and check its bindings for every target:

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
