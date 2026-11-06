"""
Builds fast, the Cython and C ways of the benchmark, against the Python
bindings of libfoo in FOO_BINDINGS, where foo.pxd and libfoo.h are, linked to
the library at FOO_LIBRARY:

  FOO_BINDINGS=output/python FOO_LIBRARY=/path/to/libfoo.so \
    python setup.py build_ext --inplace
"""

import os

from Cython.Build import cythonize
from setuptools import Extension, setup

bindings = os.path.abspath(os.environ["FOO_BINDINGS"])
library = os.path.abspath(os.environ["FOO_LIBRARY"])

extension = Extension(
    "fast",
    ["fast.pyx"],
    include_dirs=[bindings, os.path.dirname(os.path.abspath(__file__))],
    extra_compile_args=["-O2"],
    extra_link_args=[library, f"-Wl,-rpath,{os.path.dirname(library)}"],
)
setup(ext_modules=cythonize([extension], include_path=[bindings]))
