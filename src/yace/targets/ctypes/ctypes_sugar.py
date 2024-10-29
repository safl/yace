"""
Addition to ctypes, making it slightly nicer to use, including:

* gen_search_paths(libname)
  * find_library() + pkg-config

* load(libname)

* typedef additions
  * c_log_double_t
  * c_uint128
  * c_int128
  * void

TODO

* Dict-accessor for structs / unions
* Convenient typecast-helpers

Copyright (c) 2023 Simon A. F. Lund <os@safl.dk>
SPDX-License-Identifier: BSD-3-Clause
"""

import ctypes
import ctypes.util
import os
import platform
import subprocess

SHARED_EXT = {
    "linux": "so",
    "windows": "dll",
    "darwin": "dylib",
}

c_int128 = ctypes.c_ubyte * 16
c_uint128 = c_int128
void = None
if ctypes.sizeof(ctypes.c_longdouble) == 8:
    c_long_double_t = ctypes.c_longdouble
else:
    c_long_double_t = ctypes.c_ubyte * 8


class Enum(object):
    """Encapsulation of C enum"""

    pass


class Structure(ctypes.Structure):
    """Encapsulation of C structs"""

    pass


class Union(ctypes.Union):
    """Encapsulation of C union"""

    pass


def gen_search_paths(libname):
    """
    Yields search-paths for the shared library with the given 'libname'. It is
    an extension of ``ctypes.util.find_library()`` using ``pkg-config``.
    """

    path = ctypes.util.find_library(libname)
    if path:
        yield path

    try:
        proc = subprocess.run(
            ["pkg-config", libname, "--variable=libdir"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if not proc.returncode:
            ext = SHARED_EXT.get(platform.system().lower(), "so")

            yield os.path.join(
                proc.stdout.decode("utf-8").strip(), f"lib{libname}.{ext}"
            )
    except subprocess.CalledProcessError:
        pass


def load(libname):
    """Dynamically load the shared library named 'libname'"""

    for spath in gen_search_paths(libname):
        try:
            lib = ctypes.CDLL(spath)
            if lib:
                return lib
        except OSError:
            continue

    return None
