.. _sec-install-system:

System
------

It is assumed that the following tools are available on the system where
**yace** is running:

* ``clang-format`` (Version must be >= 13 to utilize style-files)
* ``gcc`` or ``clang``
* ``doxygen``
* ``graphviz`` (The ``dot`` tool from this package is needed by ``doxygen``
* ``make`` to do a lot of things in a more convenient way

There are scripts in ``toolbox/pkgs/`` installing the above-mentioned tools on
Ubuntu and macOS.

Development
~~~~~~~~~~~

The toolbox and Makefile-helper requires that ``make`` is available. See the
utilities provided by running:

.. literalinclude:: 900_make.txt
   :language: bash
   :lines: 1-

This should output:

.. literalinclude:: 900_make.out
   :language: bash
   :lines: 1-
