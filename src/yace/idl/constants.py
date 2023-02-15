#!/usr/bin/env python3
"""
The **yace** constants consists of:

* Constant Values:

  * :class:`yace.idl.constants.String`
  * :class:`yace.idl.constants.Dec`
  * :class:`yace.idl.constants.Hex`

* Symbolic Constants:

  * :class:`yace.idl.constants.Define`

* Enum Types:

  * :class:`yace.idl.constants.Enum`
  * :class:`yace.idl.constants.EnumValue`

Their idl representation follows below.
"""
import typing

from .base import Documented, Entity, Named


class String(Entity):
    """
    Representation of a literal string e.g. in C::

        "this is a string-literal"

    """

    cls: str = "str"
    lit: str

    def is_valid_lit(self):
        if not isinstance(self.lit, str):
            return False, f"Unsupported lit[{self.lit}]"

        return True, None


class Hex(Entity):
    """
    Representation of a hexadecimal constant

    The emitted C code should be hexadecimal notation of literal integer
    values, such as those used by :class:`yace.idl.constants.Define` and
    :class:`yace.idl.enumtypes.Enum`::

        #define FOO 0xACDC

    """

    cls: str = "hex"
    lit: int

    def is_valid_lit(self):
        if not isinstance(self.lit, int):
            return False, f"Unsupported lit[{self.lit}]"

        return True, None


class Dec(Entity):
    """Representation of a an integer literal in decimal"""

    cls: str = "dec"
    lit: int

    def is_valid_lit(self):
        if not isinstance(self.lit, int):
            return False, f"Unsupported lit[{self.lit}]"

        return True, None


class Define(Entity, Named, Documented):
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

    cls: str = "define"
    val: typing.Any


class EnumValue(Entity, Named, Documented):
    """
    Representation of values in :class:`yace.idl.constants.Enum`.

    By default, the C emitter produces::

        SYMBOL = lit.val

    for the :class:`yace.idl.constants.EnumValue`.
    """

    cls: str = "enum_value"
    val: typing.Any = None

    def is_valid_val(self):
        """Checks whether the :class:`yace.idl.constants.EnumValue` is valid"""

        if not isinstance(self.val, (Dec, Hex)):
            return (
                False,
                f"EnumValue[{self.sym}][Unsupported Instance]: {self.val}",
            )

        return (True, None)


class Enum(Entity, Named, Documented):
    """
    Representation of enumeration values, note that literals on the
    :class:`yace.idl.constants.EnumValue` are optional, an
    :class:`yace.idl.constants.Enum` with **non** literal
    :class:`yace.idl.constants.EnumValue` looks like::

        enum example {
            FOO,
            BAR,
            BAZ,
        };

    Whereas, an :class:`yace.idl.constants.Enum` with **literal**
    :class:`yace.idl.constants.EnumValue` looks like::

        enum example {
            FOO = 0xACDC,
            BAR = 0x1337,
            BAZ = 0xBEEF,
        };

    for the :class:`yace.idl.constants.EnumValue``.
    """

    cls: str = "enum"
    members: typing.List[EnumValue]

    def is_valid_members(self):
        """Checks whether the :class:`yace.idl.constants.Enum` is valid"""

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
