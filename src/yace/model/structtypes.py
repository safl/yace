#!/usr/bin/env python3
"""
Entities are the base classes representing the language constructs of C APIs in
the :class:`yace.model.interface.Model`. The entities serve as encapsulated
type-checking of YAML-definitions of the language model.
"""
import typing

from .base import Declaration, Typespec


class Bits(Declaration):
    """Representation of a :class:`.Bitfield` member."""

    cls: str = "bits"


class Bitfield(Declaration):
    """Representation of enumerations / collections of constants"""

    cls: str = "bitfield"
    members: typing.List[Bits] = []

    def is_valid(self):
        """Checks whether the bitfield members match the width"""

        invalid_types = [type(m) for m in self.members if not isinstance(m, Bits)]
        if len(invalid_types):
            return (
                False,
                f"Invalid types in {self.sym}.members; "
                "expecting: Bits, got: [{invalid_types}]",
            )

        acc = sum([m.width for m in self.members])
        if acc != self.dtype.width:
            return (False, f"Aacumulated width({acc}) != {self.dtype.width}")

        return (True, None)


class Field(Declaration):
    """
    :class:`yace.model.Field` represents members of :class:`yace.model.Struct`
    and :class:`yace.model.Union`, utilized by compiler to emit code in the C
    API similar to::

        uint32_t bar;

    That is, within a ``struct/union`` block e.g.::

        struct foo {
            uint32_t bar;
        };

    The 'dtype' and 'width' members are utilized to produce a fitting
    type-declaration for the target language, as in the examples above for C.
    """

    cls: str = "field"
    fmt: str = "%u"


class Struct(Declaration):
    """Representation of enumerations / collections of constants"""

    cls: str = "struct"
    members: typing.List = []
