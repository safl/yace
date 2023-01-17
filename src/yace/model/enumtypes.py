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

    val: typing.Union[LiteralDec, LiteralHex] = None

    cls: str = "enum_value"
    lbl: str = "default"

    def is_valid(self):
        """Checks whether the :class:`.EnumValue` is valid"""

        if not isinstance(self.val, (LiteralDec, LiteralHex)):
            return (
                False,
                f"EnumValue[{self.sym}][Unsupported Instance]: {self.val}",
            )

        return (True, None)


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
    lbl: str = "default"

    def is_valid(self):
        """Checks whether the :class:`.Enum` is valid"""

        invalid_types = [type(m) for m in self.members if not isinstance(m, EnumValue)]
        if len(invalid_types):
            return (
                False,
                f"Invalid types in {self.sym}.members; "
                "expecting: EnumValue, got: [{invalid_types}]",
            )

        if LiteralString in [type(m) for m in self.members]:
            return (False, "Enum-values must be numeral-types")

        return (True, None)
