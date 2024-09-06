.. _sec-usage:

=======
 Usage
=======

Running **yace** requires that you have:

1. Installed **yace** and auxilary :ref:`sec-tools`
2. A :ref:`sec-idl` file describing your C API or a Yace-compatible C-header

To satisfy the first point, then see :ref:`sec-install`. For the second
point, then you can consult :ref:`sec-idl` for reference to define
a :ref:`sec-idl-files` from scratch.

Command-Line Interface
======================

Invoking the command-line interface of **yace**:

.. literalinclude:: 050_yace_help.cmd
   :language: yaml
   :lines: 1-

looks like

.. literalinclude:: 050_yace_help.out
   :language: yaml
   :lines: 1-

.. note::
   Notice that unless an error occurs then **yace** is silent. To make **yace**
   chatty, then increase the log-level using the arguments: ``-l`` / ``-ll`` /
   ``-lll``.

Example
=======

To get a quick sense of **yace** then you can utilize this simple example:

.. literalinclude:: ../../../models/example.yaml
   :language: yaml
   :caption:
   :lines: 1-

With it, invoke **yace** like so:

.. literalinclude:: 200_example.cmd
   :language: bash
   :lines: 1-

**yace** will then populate the output-directory ``output`` with the following
emitted code and artifacts:

.. literalinclude:: 300_output.out
   :language: bash
   :lines: 1-

Example: capi
-------------

The C API header generated from the above looks like:

.. literalinclude:: output/capi/libfoo_core.h
   :language: c
   :caption:
   :lines: 1-

The emitted C header above has been modified by ``clang-format`` after it was
emitted. This is one of the **stages** that a **yace** target goes through by
default.

.. literalinclude:: 100_example_nofmt.cmd
   :language: bash
   :lines: 1-

The above will do nothing else but emit code. See ``yace --help`` for the
different stages.

Example: ctypes
---------------

The ``ctypes`` target produces the following:

.. literalinclude:: output/ctypes/example.py
   :language: Python
   :caption:
   :lines: 1-

Note, this is early stage of the :ref:`sec-targets-ctypes` target.

Additional Examples
===================

For more elaborate examples, then take a look at:

* The idls in the **yace** repository at
  https://github.com/safl/yace/tree/main/models
* The target-specific output in the :ref:`sec-targets` section
* The artifacts produces on the :github-yace-actions:`GitHUB Actions Page <>`
