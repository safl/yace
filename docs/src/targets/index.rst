.. _sec-targets:

=========
 Targets
=========

A target generates the code of an API, from its IR, for one language, and
checks it: that it builds, that its records have the layout recorded in the IR,
and that it works. Targets are found through the ``yace.targets`` entry point
group, so a package can provide one without changes to **yace**; see
:py:mod:`yace.targets.target`.

The C target is the one available. Python, Rust, Zig and C++ are planned, each
generating bindings idiomatic for its language from the same IR.

.. toctree::
   :maxdepth: 2
   :hidden:

   capi/index.rst

.. automodule:: yace.targets.target
   :members:
