"""
The enumeration types consists of Enumerations (:class:`Enum`) and their values
:class:`EnumValue`. The values themselves are literals: :class:`LiteralDec`,
:class:`LiteralHex` and :class:`LiteralString`.
"""
import typing
from dataclasses import dataclass, field

from .entities import Entity
from .literals import LiteralDec, LiteralHex, LiteralString


@dataclass
class EnumValue(Entity):
    """
    Representation of values in :class:`.Enum`.

    By default, the C emitter produces::

        SYMBOL = lit.val

    for the :class:`EnumValue``.
    """

    lit: typing.Union[LiteralDec, LiteralHex, LiteralString] = None

    cls: str = "enum_value"


@dataclass
class Enum(Entity):
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

    members: typing.List[EnumValue]

    cls: str = "enum"
