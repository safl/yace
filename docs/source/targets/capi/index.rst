.. _sec-targets-capi:

capi
====

The **yace** emitter target, named ``capi``, produces a C API consisting of the
following files:

* ``lib{meta.prefix}.h``        -- Library header bundle
* ``lib{meta.prefix}_core.h``   -- The core API declarations
* ``lib{meta.prefix}_pp.h``     -- Pretty-printer definitions
* ``{meta.prefix}_pp.c``        -- Pretty-printer implementation

And, not part of the API itself is:

* ``{meta.prefix}_check.c``     -- ``main()`` program checking generated code

The following section shows the details of how to generate a C API from a
**yace** interface definition language :ref:`sec-idl-files` file.

.. _sec-targets-capi-example:

Example
-------

Below, **yace** is invoked on the ``idls/example.yaml`` from the **yace**
git-repository.

.. literalinclude:: 200_yace.cmd
   :language: yaml
   :lines: 1-

.. literalinclude:: 300_output.out
   :language: yaml
   :lines: 1-

Describe the parts of the generated output. Show the content of the most
interesting parts

.. _sec-targets-capi-example-headers:

C API
~~~~~

.. literalinclude:: ../../../../output/capi/libfoo.h
   :language: c
   :caption:
   :lines: 1-

.. literalinclude:: ../../../../output/capi/libfoo_core.h
   :language: c
   :caption:
   :lines: 1-

.. _sec-targets-capi-example-pp:

Pretty-printers
~~~~~~~~~~~~~~~

.. literalinclude:: ../../../../output/capi/libfoo_pp.h
   :language: c
   :caption:
   :lines: 1-

.. literalinclude:: ../../../../output/capi/foo_pp.c
   :language: c
   :caption:
   :lines: 1-

.. _sec-targets-capi-example-check:

Check
~~~~~

.. literalinclude:: ../../../../output/capi/foo_check.c
   :language: c
   :caption:
   :lines: 1-

This ``foo_check.c`` is built using the :class:`.Gcc` tool, to check whether
headers are well-behaved. Thus a file ``a.out`` exists which is executable
result of translatning the source-file above.

When running it:

.. literalinclude:: 400_check.cmd
   :language: yaml
   :lines: 1-

You can see textual representation of ``struct``/``union`` produced by the
pretty-printers work:

.. literalinclude:: 400_check.out
   :language: yaml
   :lines: 1-

.. _sec-targets-capi-example-aux:

Example: Auxilary files
-----------------------

The auxilary files consists of:

* Doxygen output HTML report ``output/capi/doxyreport/html/index.html``
* Clang-format style-files ``output/capi/clang-format*``
* Tool log-files ``output/capi/*.log``

System Tools
------------

The ``capi`` target uses the following tools:

* :class:`yace.tools.ClangFormat`
* :class:`yace.tools.Doxygen`
* :class:`yace.tools.Gcc`

To do what the tools does best, format the emitted code, produce Doxygen
documentation project and build it, and lastly build the verification-program
and run it.

Implementation
--------------

.. automodule:: yace.targets.capi.target
   :inherited-members:
   :members:
   :undoc-members:
