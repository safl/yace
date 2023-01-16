#!/usr/bin/env python3
"""
Literals are at the heart of every language, with **yace** the following are
expressed:

* :class:`LiteralString`
* :class:`LiteralHex`
* :class:`LiteralDec`

These emit the usual suspects::

    #define PROJECT_DESCRIPTION "This is a literal string"

    enum jazz {
        FOO = 0xACDC,
        BAR = 0x1337,
        BAZ = 0xBEEF,
    };

    #define THRESHOLD 1337

The intent of these literals is just add a level of control to the values in
the entities :class:`.enumtypes.EnumValue` and :class:`entities.Define`.
"""
import typing
from dataclasses import dataclass, field


@dataclass
class LiteralString:
    """
    Representation of a an literal string e.g. in C::

        "this is a literal string"

    """

    lit: str
    cls: str = "str"

    def is_valid(self):

        if not isinstance(self.lit, str):
            return (False, f"Unsupported lit[{self.lit}]")

        return (True, None)


@dataclass
class LiteralHex:
    """
    Representation of a an integer literal

    The emitted C code should be hexidecimal notation of literal integer
    values, such as those used by :class:`yace.model.macros.Define` and
    :class:`yace.model.enumtypes.Enum`::

        #define FOO 0xACDC

    """

    lit: int
    cls: str = "hex"

    def is_valid(self):
        if not isinstance(self.lit, int):
            return (False, f"Unsupported lit[{self.lit}]")

        return (True, None)


@dataclass
class LiteralDec:
    """Representation of a an integer literal in decimal"""

    lit: int
    cls: str = "dec"

    def is_valid(self):
        if not isinstance(self.lit, int):
            return (False, f"Unsupported lit[{self.lit}]")

        return (True, None)
