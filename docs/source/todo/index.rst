.. _sec-todo:

======
 TODO
======

This is a quick'n'dirty notes on things to do:

* Add a model-checker

  * Check that no duplicate symbols exists
  * Check that bitfields are within bounds and matching their parent type
  * Add runtime-checkig of the types in the dataclasses

* Automate generation of documentation exampels

  * The examples in the documentation does use ``kmdo`` ``.cmd`` files,
    however, they are not exectued during the CI run. This should be fixed, as
    they will otherwise go stale...
