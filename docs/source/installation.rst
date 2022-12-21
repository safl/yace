.. _sec-installation:

Installation
============

**yace** relies on a handful of tools and libraries to do what it does. The
tools include, C compilers, documentation generators, and build-tools.

The system tools are covered in the following section and the Python
environment in the section after that.

System
------

It is assumed that the following tools are available on the system where
**yace** is running:

* ``clang-format`` (Version must be >= 13 to utilize style-files)
* ``gcc`` or ``clang``
* ``doxygen``
* ``graphviz`` (The ``dot`` tool from this package is needed by ``doxygen``
* ``make`` to do a lot of things in a more convenient way

There are scripts in ``toolbox/pkgs/`` installing the above-mentioned tools on
Ubuntu and macOS.

Python
------

And a **Python** environment with

* ``Python 3.7+`` and the modules

  * ``jinja2``
  * ``yaml``

Once they are installed, then run::

  make all

This will build and install ``yace``, and its Python package dependencies,
using ``python3 -m pip --user ...``, thus make sure that you have ``PATH``
confidered to something like::

  echo "export PATH=$(python -m site --user-base)/bin" >> $HOME/.bash_profile
