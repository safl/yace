#!/usr/bin/env python3
"""
The **yace** constants consists of:

* Constant Values:

  * :class:`yace.ir.constants.String`
  * :class:`yace.ir.constants.Dec`
  * :class:`yace.ir.constants.Hex`

* Symbolic Constants:

  * :class:`yace.ir.constants.Define`

* Enum Types:

  * :class:`yace.ir.constants.Enum`
  * :class:`yace.ir.constants.EnumValue`

Their ir representation follows below.
"""
from typing import List, Union

from .base import Documented, Entity, Named


class String(Entity):
    """
    Representation of a literal string e.g. in C::

        "this is a string-literal"

    """

    key: str = "str"
    lit: str


class Hex(Entity):
    """
    Representation of a hexadecimal constant

    The emitted C code should be hexadecimal notation of literal integer
    values, such as those used by :class:`yace.ir.constants.Define` and
    :class:`yace.ir.enumtypes.Enum`::

        #define FOO 0xACDC

    """

    key: str = "hex"
    lit: int


class Dec(Entity):
    """Representation of a an integer literal in decimal"""

    key: str = "dec"
    lit: int


class Define(Entity, Named):
    """
    C MACROS, one of biggest headaches when it comes to FFI interfaces,
    especially for interpreted languages such as Python, since
    MACRO-expressions have no symbols to "call" as these are all
    pre-preprocossed and gone thus, no longer available.

    Thus, **yace** only support the definition of MACRO values, such as::

        #define SOME_GLOBALLY_CONSTANT 0xACDC

    Definitions such as these to translate fairly when into equivalent globally
    available and constant constructs in other languages
    """

    key: str = "define"
    val: Union[String, Hex, Dec]


class EnumValue(Entity, Named, Documented):
    """
    Representation of values in :class:`yace.ir.constants.Enum`.

    By default, the C emitter produces::

        SYMBOL = lit.val

    for the :class:`yace.ir.constants.EnumValue`.
    """

    key: str = "enum_value"
    val: Union[Hex, Dec]


class Enum(Entity, Named, Documented):
    """
    Representation of enumeration values, note that literals on the
    :class:`yace.ir.constants.EnumValue` are optional, an
    :class:`yace.ir.constants.Enum` with **non** literal
    :class:`yace.ir.constants.EnumValue` looks like::

        enum example {
            FOO,
            BAR,
            BAZ,
        };

    Whereas, an :class:`yace.ir.constants.Enum` with **literal**
    :class:`yace.ir.constants.EnumValue` looks like::

        enum example {
            FOO = 0xACDC,
            BAR = 0x1337,
            BAZ = 0xBEEF,
        };

    for the :class:`yace.ir.constants.EnumValue``.
    """

    key: str = "enum"
    members: List[EnumValue]

    def is_valid_members(self):
        """Checks whether the :class:`yace.ir.constants.Enum` is valid"""

        invalid_types = [type(m) for m in self.members if not isinstance(m, EnumValue)]
        if len(invalid_types):
            return (
                False,
                f"Invalid types in {self.sym}.members; "
                "expecting: EnumValue, got: [{invalid_types}]",
            )

        if String in [type(m) for m in self.members]:
            return (False, "Enum-values must be numeral-types")

        return (True, None)
