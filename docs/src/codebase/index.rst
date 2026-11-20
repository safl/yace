.. SPDX-FileCopyrightText: Simon A. F. Lund <os@safl.dk>
..
.. SPDX-License-Identifier: GPL-2.0-only

.. _sec-codebase:

==========
 Codebase
==========

The parts of the codebase which are not described elsewhere: the
:ref:`sec-codebase-cli` and the :ref:`sec-codebase-compiler` running the
targets. The IR is described in :ref:`sec-ir-entities`, and the targets in
:ref:`sec-targets`.

.. _sec-codebase-toolbox:

Toolbox
=======

The toolbox and the Makefile require that ``make`` is available. See the
utilities they provide by running:

.. literalinclude:: 900_make.txt
   :language: bash
   :lines: 1-

``make help`` prints:

.. literalinclude:: 900_make.out
   :language: ansi-color
   :lines: 1-

.. _sec-codebase-devenv:

Development environment
=======================

The development environment is a container image, built from
``toolbox/devenv/Containerfile``: Ubuntu with every toolchain a target checks
its bindings with, at pinned versions. That includes the Rust of the
``rust-version`` the generated ``Cargo.toml`` declares, which the tests build
the fixture's Rust checks with. The tag of the image is a digest of what it is
built from, and the image is published as ``ghcr.io/safl/yace-devenv``. The
following command starts a shell in it, as your own user, with the repository
at ``/yace``::

  make devenv-shell

The following command runs a command in it, as CI runs those of its Linux jobs
that need the toolchains::

  make devenv-run CMD="make deps build install test PYTHON=python3.13"

As for any make variable, a ``$`` in ``CMD`` is written ``$$``.

With ``make devenv-pull`` you get the image of the tree you have checked out,
and after changing ``toolbox/devenv`` you build it with ``make devenv``. Podman
is used when installed, Docker otherwise; set ``CONTAINER`` to choose.

CI pushes the image when the registry has none of its tag. A package that CI
creates is private, so a maintainer makes it public once, for ``make
devenv-pull`` to work without logging in. A pull request from a fork cannot
push, so one changing ``toolbox/devenv`` fails until the change is pushed from
the repository itself.

The macOS jobs of CI cannot run containers. They use the toolchains of the
runner, with Python, Zig and Go installed by their actions.

main requires one check of a pull request, ``ci-result``. That job of the
``verify_and_publish`` workflow fails unless every other job of the workflow
succeeded. A change of only ``docs/`` and Markdown files skips the jobs that
build and test, and the ``docs`` workflow builds it.

The tests build the module and the ``.pxd`` of the Cython target with Cython,
and check the stub with mypy. The tests of the Cython check and of the Cython
benchmark of ``examples/libfoo`` build with pip and meson-python. ``make
install`` installs Cython, meson-python, meson, ninja and mypy into the
environment of **yace** at the versions the ``Makefile`` pins, so the Linux
and macOS jobs both have them. The tests put the scripts of that environment
first on the ``PATH``, where meson finds meson, ninja and cython.

TOC
===

.. toctree::
  :maxdepth: 2

  cli.rst
  compiler.rst
