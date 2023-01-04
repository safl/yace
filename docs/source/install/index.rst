.. _sec-install:

Install
=======

The **yace** command-line tool is implemented in :Python:`Python <>`. It
requires :Python:`Python <>` 3.7+ along with the third-party modules:
:pyyaml:`pyyaml <>` and :jinja2:`jinja2 <>`. **yace** is distributed via the
Python Package Index and thus installable by:

.. literalinclude:: 000_install.cmd
   :language: bash
   :lines: 1-

Once installed, you should be able to run **yace** via the command-line, e.g.:

.. literalinclude:: 100_help.cmd
   :language: bash
   :lines: 1-

The command above should print the output below:

.. literalinclude:: 100_help.out
   :language: bash
   :lines: 1-

In case it does not, then check your :Python:`Python <>` environment, in case
it is due to an error with **yace** then please submit an issue on
:github-yace-issues:`GitHUB <>`.

.. note:: A common issue with the above approach is that you get an error
   message lige ``command not found: yace``, this is because ``yace`` is not in
   in one of the locations that the ``PATH`` environment variable is pointing
   to.  Make sure that it is by adding the Python bin location to ``PATH``::

     echo "export PATH=$(python -m site --user-base)/bin" >> $HOME/.bash_profile

The above is all that is needed for the code-emission functionality of
**yace**, however, to take things a bit further then **yace** utilizes a
handful of other tools, compilers, build-systems and documentation generators.

.. toctree::
   :maxdepth: 2
   :hidden:

   system.rst
