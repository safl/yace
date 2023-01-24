#!/usr/bin/env python3
"""
Union Types behave the same as :class:`.structtypes.Struct`. The difference are
simply that they represent the declaration of a C Union rather than a C Struct.
"""
import typing

from .base import Typespec


class Union(Typespec):
    """Representation of enumerations / collections of constants"""

    members: typing.List = []

    cls: str = "union"
