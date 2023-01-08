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

.. literalinclude:: output/libexample.h
   :language: c
   :caption:
   :lines: 1-

The emitted C header above has been modified by ``clang-format`` after it was
emitted. When you run this locally, expect the emitted code to look slightly
different, or just run ``clang-format`` using the definitions in the **yace**
repository::

  clang-format --style=file:../clang-format-h -i output/*.h

Additional Examples
===================

For more elaborate examples, then take a look at the models in the **yace**
repository at https://github.com/safl/yace/tree/main/models. Additionally, the
artifacts produces by **yace's** on the :github-yace-issues:`GitHUB Actions
Page <>` has the output from all the models.
