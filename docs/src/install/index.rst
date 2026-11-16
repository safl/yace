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

Once installed, you should be able to run **yace** via the command-line, e.g.:

.. literalinclude:: 100_help.cmd
   :language: bash
   :lines: 1-

The above should produce the output below:

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

     # Re-login, source your shell-config, or start a new shell, eg
     $SHELL

   These commands are for a bash-like shell; adjust them to your environment.

Installing **yace** is all that its code emission needs. Beyond that, **yace**
uses other tools: compilers, build systems and documentation generators.

.. _sec-install-tools:

Install: tools
--------------

Parsing headers needs nothing more; the libclang it uses is installed with
**yace**. Checking generated code needs the compiler of the target language,
for the C target a C compiler, ``cc`` or what ``$CC`` names.

Dockerized Build
----------------

The devenv image has every toolchain that the checks of the targets use, and
CI runs the tests in it. The following command starts a shell in it, with the
repository at ``/yace``, see :ref:`sec-codebase-devenv`::

  make devenv-shell
