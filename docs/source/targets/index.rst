.. _sec-targets:

=========
 Targets
=========

The **yace** emitter targets are encapsulations of the various components
needed in **yace** to add support for a foreign-function-interface or a C
API/ABI variant.

Ideally, then targets could be defined externally from the yace code-base and
possibly just be small variations to the targets provided with yace. However,
at the moment, such pluggable infratructure is not implemented, and one has to
add the target as part of the targets in the yace package.

* Ensure that ``yets`` are pluggable

  * Produce a cookie-cutter template to create the boiler-plate for a new **yet**
  * Distribute **yets** via PyPI e.g. ``yace-yet-zig``

For now, this part of **yace** is tied into a single instance of the
code-emitter. However, this pat of the docs are provided to briefly describe
the roadmap and intent of **yace**.

A good handful of subsections are provided here, however, they are
documentation placeholders as they are yet to be written.

.. toctree::
   :maxdepth: 2
   :hidden:

   capi/index.rst
   cgo/index.rst
   cpp/index.rst
   ctypes/index.rst
   cython/index.rst
   rust/index.rst
   zig/index.rst
