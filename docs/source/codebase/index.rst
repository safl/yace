.. _sec-codebase:

==========
 Codebase
==========

This is a quick documentation-draft for the parts of the codebase which is not
directly user-facing. That is, the argumenting-parsing of the
:ref:`sec-codebase-cli`, the logic-dispatch of the
:ref:`sec-codebase-compiler`, and the encapsulation of ``yidl`` / ``Entities``
in the :ref:`sec-codebase-model`.

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
   :language: bash
   :lines: 1-

TOC
===

.. toctree::
  :maxdepth: 2

  cli.rst
  compiler.rst
  model.rst
