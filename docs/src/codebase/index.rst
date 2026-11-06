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

The toolbox and Makefile-helper requires that ``make`` is available. See the
utilities provided by running:

.. literalinclude:: 900_make.txt
   :language: bash
   :lines: 1-

This should output:

.. literalinclude:: 900_make.out
   :language: ansi-color
   :lines: 1-

.. _sec-codebase-devenv:

Development environment
=======================

The development environment is a container image, built from
``toolbox/devenv/Containerfile``: Ubuntu with every toolchain a target checks
its bindings with, at pinned versions. That includes the Rust of the
``rust-version`` the generated ``Cargo.toml`` declares, which the tests build the
fixture's Rust checks with. Its tag is a digest of what it is built from, and it
is published as ``ghcr.io/safl/yace-devenv``. A shell in it, as your own user,
with the repository at ``/yace``::

  make devenv-shell

Or a command, as CI runs those of its Linux jobs that need the toolchains::

  make devenv-run CMD="make deps build install test PYTHON=python3.13"

As for any make variable, a ``$`` in ``CMD`` is written ``$$``.

With ``make devenv-pull`` you get the image of the tree you have checked out, and
after changing ``toolbox/devenv`` you build it with ``make devenv``. Podman is
used when installed, Docker otherwise; set ``CONTAINER`` to choose.

CI pushes the image when the registry has none of its tag. A package that CI
creates is private, so a maintainer makes it public once, for ``make
devenv-pull`` to work without logging in. A pull request from a fork cannot
push, so one changing ``toolbox/devenv`` fails until the change is pushed from
the repository itself.

The macOS jobs of CI cannot run containers. They use the toolchains of the
runner, with Python, Zig and Go installed by their actions.

The tests build Cython code against the .pxd of the Python target with Cython,
which ``make install`` adds to the environment of **yace**, with setuptools, at
the version the ``Makefile`` pins, so the Linux and macOS jobs alike have it.

TOC
===

.. toctree::
  :maxdepth: 2

  cli.rst
  compiler.rst
