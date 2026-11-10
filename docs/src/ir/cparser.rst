.. SPDX-FileCopyrightText: Simon A. F. Lund <os@safl.dk>
..
.. SPDX-License-Identifier: GPL-2.0-only

.. _sec-ir-cparser:

C Parser
========

Given a C header, ``yace`` parses it into the IR with libclang. Any header can
be parsed; everything that can be represented is, and every place the header
steps outside the C subset is reported as a diagnostic, naming the rule, see
:ref:`sec-ir-rules`. Nothing is dropped or changed without one.

Invoking it on the example library:

.. literalinclude:: 400_cparser.cmd
   :language: bash

C Header
--------

.. literalinclude:: ../../../examples/libfoo/include/foo.h
   :language: c
   :caption:

IR
--

.. literalinclude:: ../../../output/foo.yaml
   :language: yaml
   :caption:

.. _sec-ir-cparser-implementation:

Implementation
--------------

.. automodule:: yace.ir.cparser
   :members:

Semantics
---------

.. automodule:: yace.ir.semantics
   :members:
