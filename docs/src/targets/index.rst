.. _sec-targets:

=========
 Targets
=========

A target generates the code of an API, from its IR, for one language, and
checks it: that it builds, that its records have the layout recorded in the IR,
and that it works. Targets are found through the ``yace.targets`` entry point
group, so a package can provide one without changes to **yace**; see
:py:mod:`yace.targets.target`.

Each target has two layers. The raw one calls the C functions as they are,
and needs nothing beyond the declarations. The idiomatic one, over it, is what
a programmer of the language expects: handles released when they go out of
scope, errors raised or returned, results returned rather than written through
pointers, closures for callbacks. It is generated from what the header says
beyond C, see :ref:`sec-ir-csubset`, as derived in :py:mod:`yace.targets.idiom`,
the same for every language.

The targets available are C, :ref:`sec-targets-capi`, Python,
:ref:`sec-targets-python`, and Rust, :ref:`sec-targets-rust`. Zig and C++ are
planned, each generating bindings idiomatic for its language from the same IR.

The fixture
===========

What a target's own check cannot show is that the bindings work with a library
built from the original header. The example library, ``examples/libfoo``, uses
every construct of the C subset, and is that library. Each target has a check
program in ``examples/libfoo/checks/<target>/``, written in the target's
language against the bindings it generates. The program calls the library,
exercising callbacks, out-parameters, opaque handles, strings and records, and
prints what it got back. Records are printed with the pretty-printers the target
generates.

All checks print the same YAML documents, those in
``examples/libfoo/expected.yaml``, or the same as JSON objects when given the
argument ``json``. ``tests/test_fixture.py`` builds the library as a shared
library, generates each target's bindings, builds and runs its check, and
compares the output to the expected documents.

The expected documents are what the library returns, so they hold no pointer
values, which differ between runs.

.. toctree::
   :maxdepth: 2
   :hidden:

   capi/index.rst
   python/index.rst
   rust/index.rst

.. automodule:: yace.targets.target
   :members:

.. automodule:: yace.targets.idiom
   :members:
