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

    val: str
    cls: str = "str"


@dataclass
class LiteralHex:
    """Representation of a an integer literal"""

    val: int
    cls: str = "hex"


@dataclass
class LiteralDec:
    """Representation of a an integer literal in decimal"""

    val: int
    cls: str = "dec"
