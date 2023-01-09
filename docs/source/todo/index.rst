.. _sec-todo:

======
 TODO
======

This is a quick'n'dirty notes on things to do:

* Add function-declarations

  * Must be added to yim
  * And added to ``yet``

* Add a model-checker

  * Check that no duplicate symbols exists
  * Check that bitfields are within bounds and matching their parent type
  * Add runtime-checkig of the types in the dataclasses

* Add negative-tests

  * Currently, running yace with the example test-cases covers 97% of the code,
    however, it would be good to organize this with py.test
  * Once organized then the execution of yace can be done via various
    entry-points: ``python3 -m yace example-yim.yaml`` and ``yace
    example-yim.yaml``

* Add ``yet``-implementations, in order of priority

  * capi
  * ctypes
  * cython as these are needed by
  * These ``yets`` first as they are the main motivation of **yace** itself, to
    solve those FFI and pretty-printer headaches for :xnvme:`xnvme <>`.
  * After those, then rust, c++, and go

* Add visualization of ``yim``

  * Via invocation: ``yace example-yim.yaml --visualize``
  * This should yield a visualization of the ``yim`` with relatations
