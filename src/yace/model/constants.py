#!/usr/bin/env python3
"""
Constants, Literal Strings, and Symbolic Constants

C MACROS, one of biggest headaches when it comes to FFI interfaces, especially
for interpreted languages such as Python, since MACRO-expressions have no
symbols to "call" as these are all pre-preprocossed and gone thus, no longer
available.

Thus, **yace** only support the definition of MACRO values, such as::

    #define SOME_GLOBALLY_CONSTANT 0xACDC

Definitions such as these to translate fairly when into equivalent globally
available and constant constructs in other languages.

Literals are at the heart of every language, with **yace** the following are
expressed:

* :class:`String`
* :class:`Dec`
* :class:`Hex`

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

from .base import Declaration, Entity


class String(Entity):
    """
    Representation of a literal string e.g. in C::

        "this is a string-literal"

    """

    cls: str = "str"
    lit: str

    def is_valid(self):

        if not isinstance(self.lit, str):
            return False, f"Unsupported lit[{self.lit}]"

        return True, None


class Hex(Entity):
    """
    Representation of a hexi-decimal constant

    The emitted C code should be hexidecimal notation of literal integer
    values, such as those used by :class:`yace.model.macros.Define` and
    :class:`yace.model.enumtypes.Enum`::

        #define FOO 0xACDC

    """

    cls: str = "hex"
    lit: int

    def is_valid(self):
        if not isinstance(self.lit, int):
            return False, f"Unsupported lit[{self.lit}]"

        return True, None


class Dec(Entity):
    """Representation of a an integer literal in decimal"""

    cls: str = "dec"
    lit: int

    def is_valid(self):
        if not isinstance(self.lit, int):
            return False, f"Unsupported lit[{self.lit}]"

        return True, None


class Define(Declaration):
    """
    Representation of simple MACROs / definitions

    When emitting the C API, the Define holds information to generate things
    like::

        #define MAX_SOMETHING 128

    The other code-emitters will generate similar globally scoped definitions.
    """

    cls: str = "define"
    val: typing.Union[Dec, Hex, String]


class EnumValue(Declaration):
    """
    Representation of values in :class:`.Enum`.

    By default, the C emitter produces::

        SYMBOL = lit.val

    for the :class:`EnumValue``.
    """

    cls: str = "enum_value"
    val: typing.Union[Dec, Hex] = None

    def is_valid(self):
        """Checks whether the :class:`.EnumValue` is valid"""

        if not isinstance(self.val, (Dec, Hex)):
            return (
                False,
                f"EnumValue[{self.sym}][Unsupported Instance]: {self.val}",
            )

        return (True, None)


class Enum(Declaration):
    """
    Representation of enumeration values, note that literals on the
    :class:`.EnumValue` are optional, an :class:`.Enum` with **non** literal
    :class:`.EnumValue` looks like::

        enum example {
            FOO,
            BAR,
            BAZ,
        };

    Whereas, an :class:`.Enum` with **literal** :class:`.EnumValue` looks
    like::

        enum example {
            FOO = 0xACDC,
            BAR = 0x1337,
            BAZ = 0xBEEF,
        };

    for the :class:`EnumValue``.
    """

    cls: str = "enum"
    members: typing.List[EnumValue]

    def is_valid(self):
        """Checks whether the :class:`.Enum` is valid"""

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
