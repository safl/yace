.. _sec-targets-capi:

capi
====

The C target, ``capi``, generates the C API of the header, into
``<output>/capi``:

``lib<prefix>.h``
  The C API: the declarations of the header, and of the pretty-printers. It is
  generated from the IR, not copied from the header, and may use what C allows
  and the C subset does not. A packed record keeps its
  ``__attribute__((packed))``, which the C++ layer, including it, shares.

``<prefix>_pp.c``
  The pretty-printers. Every struct and union with fields gets
  ``<name>_fpr()``, printing to a stream, and ``<name>_pr()``, printing to
  stdout, as YAML, the default, or as JSON on one line. Every enum gets
  ``<name>_str()``, the name of a value. A field of bits, see
  :ref:`sec-ir-csubset`, is printed as a mapping on one line of its value,
  ``val``, and of each of its parts, by bit, in hexadecimal in YAML,
  ``code: {val: 0x8a05, type: 0x5, dnr: 0x1}``, and in decimal in JSON. The
  printers of the other targets print the same.

``<prefix>_check.c``
  The check, not part of the API: it asserts at compile time that every record
  with fields has the size, alignment and field offsets recorded in the IR,
  then prints a zeroed instance of each, as YAML or JSON.

``<prefix>_signatures.c``
  The check of the signatures, not part of the API: it includes the headers
  the IR was parsed from, not the generated C API, and asserts at compile time
  that each function has the type the IR gives it. Every target declares the
  functions from the IR, and C++, Go and the ``.pxd`` call them through
  ``lib<prefix>.h``, so a signature the IR got wrong fails here rather than at
  run time.

The check is built with ``$CC``, by default ``cc``, as C11 with all warnings as
errors, and run; **yace** then parses what it printed, as YAML and as JSON. The
layout is asserted only on the platform it was recorded on, the ``abi`` of the
IR's meta.

The check of the signatures is compiled, as GNU C11, with the include
directories, which hold the headers when they were given by path, or by
``-I``. Where a header is not found, **yace** warns that the signatures are not
checked, and fails nothing. It does not say whether a library was built from
these headers; that is for a tool comparing the library's ABI with them, such as
``abidiff``.

Example
-------

.. literalinclude:: 200_yace.cmd
   :language: bash
   :lines: 1-

.. literalinclude:: 300_output.out
   :language: text
   :lines: 1-

C API
~~~~~

.. literalinclude:: ../../../../output/capi/libfoo.h
   :language: c
   :caption:
   :lines: 1-

Pretty-printers
~~~~~~~~~~~~~~~

.. literalinclude:: ../../../../output/capi/foo_pp.c
   :language: c
   :caption:
   :lines: 1-

Check
~~~~~

.. literalinclude:: ../../../../output/capi/foo_check.c
   :language: c
   :caption:
   :lines: 1-

What the check printed, as YAML:

.. literalinclude:: ../../../../output/capi/check.yaml
   :language: yaml
   :lines: 1-

Implementation
--------------

.. automodule:: yace.targets.capi.target
   :members:

.. automodule:: yace.targets.capi.cgen
   :members:
