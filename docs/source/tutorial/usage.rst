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
