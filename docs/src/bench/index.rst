.. SPDX-FileCopyrightText: Simon A. F. Lund <os@safl.dk>
..
.. SPDX-License-Identifier: GPL-2.0-only

.. _sec-bench:

Benchmark
=========

The benchmark measures what a call of the C API costs through the bindings of
each target, against plain C. ``examples/libfoo/bench`` holds a program per
target, each doing the same work through the bindings **yace** generates for
it, and a :cijoe:`cijoe <>` workflow that builds and runs them all and records
the machine it ran on.

The work
--------

Each program opens a libfoo handle and adds ``FOO_POINTS_MAX`` points, 8, by
``foo_point_add_many()``, the x of each its index. It then sums the x of every
point, ``rounds`` times, in two ways:

calls
  A call of ``foo_point_get()`` per point, so one crossing of the FFI boundary
  per point.

callback
  A call of ``foo_point_visit()`` per round, with a callback written in the
  program's language, which libfoo calls once per point.

Each way is run ``repeat`` times, and the best time is kept. The program
prints its time per point and its sum, which every program must get:
``rounds`` times 28. The library is a shared library, so no compiler inlines
a call into it.

The programs, in ``examples/libfoo/bench/programs/``, by what the report names
them:

``c``
  Plain C, built with ``-O2``: the baseline the others are divided by.

``cpp``
  The idiomatic layer of the C++ target, ``handle.point_get()`` and
  ``handle.point_visit()`` with a lambda, built with ``-O2``.

``rust-raw``, ``rust-safe``
  The raw layer of the Rust target, ``foo_point_get()`` and an ``extern "C"``
  callback, and its safe layer, ``Handle::point_get()`` and a closure, built in
  release.

``zig``
  The idiomatic layer of the Zig target, ``handle.pointGet()`` and
  ``handle.pointVisit()`` with a method, built ``ReleaseFast``.

``go``
  The idiomatic layer of the Go target, ``handle.PointGet()`` and
  ``handle.PointVisit()`` with a closure, through cgo.

``python-raw``, ``python-idiomatic``
  The raw layer of the Python target, ``foo.foo_point_get()`` and a
  ``FooVisitCb``, and its idiomatic layer, ``handle.point_get()`` and a
  function, through ctypes.

``cython-raw``, ``cython-idiomatic``
  A loop in Cython calling ``foo_point_get()`` and a Cython callback through
  the ``.pxd`` of the Cython target, without the GIL; and the loops of
  ``python-idiomatic`` against the module of the Cython target; see
  :ref:`sec-targets-cython`.

Running it
----------

``bench.yaml`` is the workflow, and ``bench.toml`` says what it runs: the
``rounds``, the ``repeat``, the ``targets``, and the commands of yace and of
each toolchain. The steps of the workflow are:

``facts``
  The machine's OS, kernel, CPUs and memory, as cijoe gathers them.

``machine``
  Its CPU model, and the version of each toolchain and of yace; a missing
  toolchain fails the run.

``prepare``
  A fresh copy of libfoo in the work directory, the library built from it with
  ``-O2``, and the bindings generated from its header by yace.

``build``
  The program of each target.

``run``
  Each program, one after the other, its results gathered in
  ``results.json``. The run fails where a program leaves out a layer or way,
  or gets another sum than the one expected.

``report``
  The results as ``results.csv``, and ``report.txt``, the time per point of
  each, its ratio to C's, and the machine.

From ``examples/libfoo/bench``:

.. code-block:: bash

   cijoe bench.yaml -c bench.toml -o /tmp/bench

The output directory holds the record of the run: the facts, ``facts.toml``,
every command each step ran and what it printed, and the results in
``artifacts/``. With ``-c transport.toml``, once its address is filled in, the
same steps run on another machine over ssh, which needs yace and the
toolchains, and the results are collected where cijoe runs.

A recorded run
--------------

One run, with the defaults of ``bench.toml``, on the machine the report names.
The run is recorded, not rerun when the docs are built, so the figures do not
change with the machine that builds the docs. To record another, run the
workflow and replace ``docs/src/bench/report.txt`` with its
``artifacts/report.txt``.

.. literalinclude:: report.txt
   :language: text

What it shows
-------------

The figures separate the targets into three tiers, and nothing finer.

C++, the raw and safe Rust layers, Zig and Cython through the ``.pxd`` call
libfoo at between 0.6 and 1.4 times C's cost. The benchmark cannot order
them more finely than that, as the same C code is faster run inside the Python
process, as Cython's, than as a program of its own, as C's: where the code is
loaded moves its time by as much as any of these targets differ. The one
difference larger than that is Zig's call of ``handle.pointGet()``, about twice
C's, as it is not inlined and returns its optional through memory.

In Go, every call crosses cgo: a call costs about ten times C's, and a
callback, which crosses back into Go, about thirty times.

ctypes, whose every call goes through the interpreter, costs two orders of
magnitude more than C, and its idiomatic layer about two thirds again as much
as its raw one. Cython code calling C through the ``.pxd`` of the Cython
target has the cost of C, and the compiled module of the Cython target costs
about 84 ns a call where the idiomatic layer of ctypes costs 580 ns, see
:ref:`sec-targets-cython`.
