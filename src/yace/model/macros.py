#!/usr/bin/env python3
"""
C MACROS, one of biggest headaches when it comes to FFI interfaces, especially
for interpreted languages such as Python, since MACRO-expressions have no
symbols to "call" as these are all pre-preprocossed and gone thus, no longer
available.

Thus, **yace** only support the definition of MACRO values, such as::

    #define SOME_GLOBALLY_CONSTANT 0xACDC

Definitions such as these to translate fairly when into equivalent globally
available and constant constructs in other languages.
"""
import typing
from dataclasses import dataclass, field

from .entities import Entity
from .literals import LiteralDec, LiteralHex, LiteralString


@dataclass
class Define(Entity):
    """
    Representation of simple MACROs / definitions

    When emitting the C API, the Define holds information to generate things
    like::

        #define MAX_SOMETHING 128

    The other code-emitters will generate similar globally scoped definitions.
    """

    lit: typing.Union[LiteralHex, LiteralDec, LiteralString]

    cls: str = "define"
