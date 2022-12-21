Mechanics
---------

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
