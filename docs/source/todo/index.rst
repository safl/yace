.. _sec-todo:

======
 TODO
======

Here you will find functional expansions on the roadmap for **yace**. They are
jotted down here in a quick-n-dirty fashion, as it is somewhat simpler than
tracking this on e.g. GitHUB issues. Thus, the issue-tracker is reserved for
issue-reports, feature-requests etc. and the todo/roadmap is here:

* Add function-pointer-declarations

  * Must be added to yim
  * And added to ``yet``

* Add model-checking

  * Check that no duplicate symbols exists
  * Check that bitfields are within bounds and matching their parent type
  * Add runtime-checking of the types in the dataclasses

* Add transformation

  * To achieve simple code-emitters, then the IDL / ``yim`` needs to be close
    in representation to the generated code. Otherwise, then the **target**
    needs to take differences into account.
    One example are nested structures / unions in C, e specially with anonymous
    structs/unions. Equivalent definitions are not support by e.g. Rust.
    Consequently, then the ``yet`` needs to this into account when emitting
    code.
    A nicer approach would be to transform the IDL / ``yim`` by expanding the
    nested structs / unions. This is neat, since this is also useful for more
    than a single ``yet``.,

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
