.. _sec-install:

Install
=======

The **yace** command-line tool is implemented in :lang-python:`Python <>`. It
requires :lang-python:`Python <>` 3.7+ along with the third-party modules:
:pyyaml:`pyyaml <>` and :jinja2:`jinja2 <>`. **yace** is distributed via the
Python Package Index and thus installable by:

.. literalinclude:: 000_install.cmd
   :language: bash
   :lines: 1-

Once installed, you should be able to run **yace** via the command-line, e.g.:

.. literalinclude:: 100_help.cmd
   :language: bash
   :lines: 1-

The above should produce the output below:

.. literalinclude:: 100_help.out
   :lines: 1-1

In case it does not, then check your :lang-python:`Python <>` environment, in case
it is due to an error with **yace** then please submit an issue on
:github-yace-issues:`GitHUB <>`.

.. note::
   A common issue with the above approach is that you get an error message lige
   ``command not found: yace``, this is because ``yace`` is not in in one of
   the locations that the ``PATH`` environment variable is pointing to. When
   using ``pipx`` then this can be resovel with::

     pipx ensurepath

     # Re-login, source your shell-config, or start a new shell, eg
     $SHELL

   That is, when running bash-like shell, adjust according to your environment.

The above is all that is needed for the code-emission functionality of
**yace**, however, to take things a bit further then **yace** utilizes a
handful of other tools, compilers, build-systems and documentation generators.

.. _sec-install-tools:

Install: tools
--------------

Tools are utilized by the **yace** code-emitter :ref:`sec-targets`, each target
documents which tools they use, and for what purpose. It is not nescarry to
install all possible tools ahead of time, since **yace** will exit-early, in
case a tool is missing and inform you.

However, if you are curious, then have a look at the :ref:`sec-tools` section,
it describes all the tools currently utilized by :ref:`sec-targets`.
Additionally, then the scripts in ``toolbox/pkgs/`` install the tools on Ubuntu
and macOS. These scripts are used by the **yace** CI, thus, they have
everything needed for :ref:`sec-targets`, plus some additional packages for
ci-tasks.

Regardless or whether you choose to install the tools ahead-of-time or
just-in-time, then continue to the next section for a brief introduction to
using **yace** in the :ref:`sec-usage` section.

Dockerized Build
----------------

This is primarily a reference on how to bring up a docker-image, to test the build of **yace**::

  docker run \
    -it \
    --mount type=bind,source=$HOME/git/yace,target=/tmp/yace \
    ghcr.io/xnvme/xnvme-deps-debian-bullseye:next \
    bash
