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

TOC
===

.. toctree::
  :maxdepth: 2

  cli.rst
  compiler.rst
