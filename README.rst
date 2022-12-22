yace: Yet Another Code Emitter
==============================

When running the code-emitter(``yace``), then a **model** is loaded by reading
all the ``.yaml`` files in the ``--model`` directory. The model has the
following possibly nested entities:

* struct
* union

And non-nested entities:

* define
* enum
* pod (variable/member declaration)

And the "special":

* bitfield

The entities are scattered in ``.yaml`` files, and available under a **topic**
key. The **topic** key is nothing more than a means to organize / group
entities, similar to grouping them in a file.

The model is utilized to emit the following "code":

* A C Header, named "``{meta.prefix}.h``"  with datatype and datastructure
  definitions
* A C header, named "``{meta.prefix}_pp.h``" with function-declarations for
  pretty-printer functions
* A C source-file, named "``{meta.prefix}_pp.c``" with function-definitions for
  the pretty-printer functions

Code-emission templates are associated with the different "ltypes", e.g.
"emum.tmpl" inside the templates directory. The templates are primarily
utilizes to seperate the language-specifics for the code-emission into
self-container files. Thus, adding addiotional templates should enable emitting
definitions and helper functions for other languages.

Installation
------------

The following assumes that you have system with recent versions of the
following **tools** installed on your system:

* ``clang-format`` (Version must be >= 13 to utilize style-files)
* ``gcc`` or ``clang``
* ``doxygen``
* ``graphviz`` (The ``dot`` tool from this package is needed by ``doxygen``
* ``make`` to do a lot of things in a more convenient way

And a **Python** environment with

* ``Python 3.7+`` and the modules
  - ``jinja2``
  - ``yaml``

There are scripts in ``toolbox/pkgs/`` installing the above-mentioned tools on
Ubuntu and macOS. Once they are installed, then run::

  make all

This will build and install ``yace``, and its Python package dependencies,
using ``python3 -m pip --user ...``, thus make sure that you have ``PATH``
confidered to something like::

  echo "export PATH=$(python -m site --user-base)/bin" >> $HOME/.bash_profile

Usage
-----

Run the emitter::

  yace \
   --meta example/meta.yaml \
   --model example/model/nvme \
   --templates example/templates/c

See ``--help`` on how to change input/output.

For code-formating, then run ``clang-format``::

  clang-format --style=file:../clang-format-h -i output/*.h

Then take a look at the generated code::

  cat output/*.h | less

Or, instead of the above, then just run ``make``, it does everything above.
