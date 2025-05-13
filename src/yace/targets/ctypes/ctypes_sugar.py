"""
Addition to ctypes, making it slightly nicer to use, including:

* typedef additions
  * c_log_double_t
  * c_uint128
  * c_int128
  * void

TODO

* Convenient typecast-helpers

Copyright (c) 2023 Simon A. F. Lund <os@safl.dk>
SPDX-License-Identifier: BSD-3-Clause
"""

import ctypes

from typing import Generic, TypeAlias, TypeVar


c_int128 = ctypes.c_ubyte * 16
c_uint128 = c_int128
void: TypeAlias = None


class Enum(object):
	"""Encapsulation of C enum"""

	pass


class Structure(ctypes.Structure):
	"""Encapsulation of C structs"""

	def __getattr__(self, key):
		return super().__getattr__(key)

	pass


class Union(ctypes.Union):
	"""Encapsulation of C union"""

	def __getattr__(self, key):
		return super().__getattr__(key)

	pass


T = TypeVar("T")


class Pointer(Generic[T], ctypes._Pointer):
	"""Encapsulation of C pointer"""

	def __class_getitem__(cls, *args):
		ptrtype = ctypes.POINTER(*args)
		alias = super().__class_getitem__(ptrtype)
		return alias


FunctionPointer = ctypes.CFUNCTYPE
