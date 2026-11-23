.. SPDX-FileCopyrightText: Simon A. F. Lund <os@safl.dk>
..
.. SPDX-License-Identifier: GPL-2.0-only

==========
 Toolbox
==========

The scripts and lists that the Makefile and the development environment use:

* ``bump.py`` increments the patch version in ``src/yace/__init__.py``
* ``mkhelp.py`` prints the description of every target of the Makefile
* ``pkgs/{fedora,macos,ubuntu}.sh`` install the system packages that building,
  testing and documenting yace need
* ``devenv/`` holds the Containerfile of the development environment, the
  scripts that install Zig and Go into it, and ``tag.sh``, which prints the
  tag of the image
* ``survey/`` holds the survey of C libraries, ``survey.py``, and the lists of
  libraries that the survey parses
