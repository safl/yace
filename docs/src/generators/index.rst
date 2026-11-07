.. _sec-generators:

============
 Generators
============

A generator writes C headers, and the C sources implementing what they
declare, from something other than C, as the model of a specification, for
**yace** to take as it takes a header written by hand. Generators are found
through the ``yace.generators`` entry point group, so a project provides one
without changes to **yace**; see :py:mod:`yace.generators`.

What a generator writes is parsed with the headers given, held to the C
subset, see :ref:`sec-ir-csubset`, and its diagnostics reported, and the targets
emit and check its bindings and printers, see :ref:`sec-targets`. A generator
gets no way past those rules, so what it writes can be trusted as far as a
header can. Its sources are written for the project to build into its library;
**yace** does not build them.

A generator is run by its name, with options of the form
``<generator>.<key>=<value>``, the generator named by its ``NAME``:

.. code-block:: bash

   yace --generate spec --generator-option spec.prefix=foo --emit capi python

It writes into ``<output>/<generator>``, which is added to the include
directories, so its headers include one another by name.

Writing one
===========

A generator is a subclass of :py:class:`yace.generators.Generator`, named by
``NAME``, whose ``generate()`` writes into ``self.output`` by ``self.options``
and returns a :py:class:`yace.generators.Generated` of the headers and sources
it wrote. It is installed under the entry point group:

.. code-block:: toml

   [project.entry-points."yace.generators"]
   spec = "mypackage.generator:Spec"

A project that is no Python package, as a C library, keeps its generator in
its tree and names it by the file, or by the module where it is importable,
and the class, with nothing installed:

.. code-block:: bash

   yace --generate toolbox/spec.py:Spec --generator-option spec.prefix=foo
