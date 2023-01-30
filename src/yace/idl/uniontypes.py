#!/usr/bin/env python3
"""
Union Types behave the same as :class:`.structtypes.Struct`. The difference are
simply that they represent the declaration of a C Union rather than a C Struct.
"""
import typing

from .structtypes import Struct


class Union(Struct):
    """Representation of enumerations / collections of constants"""

    cls: str = "union"
