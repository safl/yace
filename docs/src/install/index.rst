.. SPDX-FileCopyrightText: Simon A. F. Lund <os@safl.dk>
..
.. SPDX-License-Identifier: GPL-2.0-only

.. _sec-install:

Install
=======

The **yace** command-line tool is implemented in :lang-python:`Python <>`. It
requires :lang-python:`Python <>` 3.12+. **yace** is distributed via the
Python Package Index and thus installable by:

.. literalinclude:: 000_install.cmd
   :language: bash
   :lines: 1-

Once installed, **yace** runs from the command line:

.. literalinclude:: 100_help.cmd
   :language: bash
   :lines: 1-

The command prints:

.. literalinclude:: 100_help.out
   :lines: 1-1

If the command prints something else, check your :lang-python:`Python <>`
environment. If the cause is an error in **yace**, please submit an issue on
:github-yace-issues:`GitHub <>`.

.. note::
   A common error after installing with ``pipx`` is
   ``command not found: yace``. The shell reports it when ``yace`` is not in
   any of the directories that the ``PATH`` environment variable lists. The
   following commands resolve it::

     pipx ensurepath

     # Log in again, source your shell configuration, or start a new shell:
     $SHELL

   These commands are for a bash-like shell; adjust them to your environment.

.. _sec-install-tools:

Install: tools
--------------

Parsing a header needs nothing more: the libclang that the parser uses is
installed with **yace**. Emitting Rust, Zig or Go needs the formatter of that
language, which comes with its toolchain. Checking the emitted code needs the
compiler of the target language; for the C target that is a C compiler, ``cc``
or what ``$CC`` names. ``yace --toolchains`` prints the toolchains and
formatters that **yace** finds, see :ref:`sec-usage`.

Development environment
-----------------------

The devenv image has every toolchain that the checks of the targets use, and
CI runs the tests in it. The following command starts a shell in it, with the
repository at ``/yace``, see :ref:`sec-codebase-devenv`::

  make devenv-shell
