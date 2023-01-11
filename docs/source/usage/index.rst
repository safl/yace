.. _sec-usage:

=======
 Usage
=======

Running **yace** requires that you have:

1. Installed **yace**
2. A **yace** :ref:`sec-model` file ready to provide as input

To satisfy the first point, then see :ref:`sec-install`. For the second point,
then you can consult :ref:`sec-model` for reference to define a ``yim`` from
scratch.

Example
=======

To get a quick sense of **yace** then you can utilize this simple example:

.. literalinclude:: example-yim.yaml
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

The C API header generated from the above looks like:

.. literalinclude:: output/libexample_core.h
   :language: c
   :caption:
   :lines: 1-

The emitted C header above has been modified by ``clang-format`` after it was
emitted. This is one of the **stages** that a **yace** target goes through by
default, you can control the stages via the cli, e.g. to skip the format-stage
then do:

.. literalinclude:: 100_example_nofmt.cmd
   :language: bash
   :lines: 1-

The above will do nothing else but emit code. See ``yace --help`` for the
different stages.

Additional Examples
===================

For more elaborate examples, then take a look at the models in the **yace**
repository at https://github.com/safl/yace/tree/main/models. Additionally, the
artifacts produces by **yace's** on the :github-yace-actions:`GitHUB Actions
Page <>` has the output from all the models.
