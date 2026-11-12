.. SPDX-FileCopyrightText: Simon A. F. Lund <os@safl.dk>
..
.. SPDX-License-Identifier: GPL-2.0-only

.. _sec-contributing:

Contributing
============

Fork the repository, make the change on a branch, check it as below, and
open a pull request against ``main``.

Set up
------

.. code-block:: console

   $ make install-source
   $ pipx install pre-commit

``make install-source`` installs yace from the checkout, in editable mode,
with pipx, along with pytest and the other development tools. ``make build
install`` instead builds the wheel and installs it, as CI does.

The tests build and run the check of each target, and skip a target whose
toolchain is missing: a C compiler for the C target, a C and a C++ compiler
for the C++ target, Cython for the Python target, cargo for Rust, zig and go. ``yace --toolchains`` prints the
toolchains yace finds. The devenv image, from ``toolbox/devenv``, has all of
them, and is what CI runs the tests in:

.. code-block:: console

   $ make devenv-run CMD="make install test"

Check a change
--------------

.. code-block:: console

   $ make format-all
   $ make test

``make format-all`` runs pre-commit on every file: black formats the Python,
ruff lints it, mypy checks the types, yamlfmt and actionlint check the YAML
and the workflows, and REUSE checks every file's license. ``make test`` runs
the tests with coverage. ``make example`` parses ``examples/libfoo`` strictly,
and emits and checks every target. CI runs all three, the tests in the devenv
with Python 3.12 and 3.13, and on macOS.

What a change carries
---------------------

A change carries a test that fails without the change. A test of a target
parses a header it writes itself, with the ``parse`` fixture of
``tests/conftest.py``, and runs the target's check, so that the test covers
what a compiler makes of the emitted code and not only its text.

``make docs`` builds the documentation, and runs ``kmdo`` first, which makes
again the command output the documentation shows. Commit the output it
changes with the change that changed it.

Commits
-------

Commits follow `Conventional Commits
<https://www.conventionalcommits.org/en/v1.0.0/>`_: a type, as ``feat``,
``fix`` or ``docs``, and a summary in the imperative mood. The body says
why the change is made, in one to three paragraphs, ideally one. The body
does not describe the diff, and does not say what was built, run or tested;
that belongs in the pull request description. Lines are at most 78
characters.

A commit message and the source code do not refer to an issue, a pull
request or anything else the hosting service numbers or links, and do not
use closing keywords such as ``Fixes #123``. Name the behaviour, the
function or the commit instead, and name a commit by its abbreviated hash
and its summary. The history is cloned, mirrored and read offline, where
such a reference names nothing.

Sign off each commit with ``git commit -s``. The sign-off acknowledges the
`Developer Certificate of Origin <https://developercertificate.org/>`_:
that you wrote the change, or have the right to pass it on under the
project's license. When a coding agent helped make a change, the commit
says so in an ``Assisted-by:`` trailer before the sign-off, naming the
agent and the language model actually used, and any analysis tool after
them, separated by spaces:

.. code-block:: text

   Assisted-by: Claude Code:claude-opus-5-5
   Signed-off-by: Full Name <address>

The trailer is the only disclosure. Do not add a ``Co-Authored-By:``
trailer for an agent, and do not add "Generated with" or similar prose to a
commit message or a pull request description. You answer for such a change
as for any other.

A release is the last commit of its pull request: ``ver: bump to vX.Y.Z``
with its section of ``CHANGELOG.md``. Merging that pull request publishes
the release to PyPI. The maintainer makes the releases.
