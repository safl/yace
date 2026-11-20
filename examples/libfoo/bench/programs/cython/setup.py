# SPDX-FileCopyrightText: Simon A. F. Lund <os@safl.dk>
#
# SPDX-License-Identifier: GPL-2.0-only

"""
Builds the Cython benchmark against the Cython bindings of libfoo in
FOO_BINDINGS, where foo.pyx, foo.pxd and libfoo.h are, linked to the library
at FOO_LIBRARY, compiled with the flags of FOO_CFLAGS, after those of the
Python: fast, calling C through foo.pxd, and foo, the module of the bindings

  FOO_BINDINGS=output/cython FOO_LIBRARY=/path/to/libfoo.so FOO_CFLAGS=-O3 \
    python setup.py build_ext --inplace
"""

import os

from Cython.Build import cythonize
from setuptools import Extension, setup

bindings = os.path.abspath(os.environ["FOO_BINDINGS"])
library = os.path.abspath(os.environ["FOO_LIBRARY"])
common = dict(
    include_dirs=[bindings],
    extra_compile_args=os.environ.get("FOO_CFLAGS", "-O3").split(),
    extra_link_args=[library, f"-Wl,-rpath,{os.path.dirname(library)}"],
)

extensions = [
    Extension("fast", ["fast.pyx"], **common),
    Extension("foo", [os.path.join(bindings, "foo.pyx")], **common),
]
setup(ext_modules=cythonize(extensions, include_path=[bindings]))
