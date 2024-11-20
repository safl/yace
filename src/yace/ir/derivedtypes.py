#!/usr/bin/env python3
"""
The **yace** derived types consists of:

* :class:`yace.ir.derivedtypes.Struct` with :class:`.Field` members

* :class:`yace.ir.derivedtypes.Bitfield` with :class:`.Bits` members

* :class:`yace.ir.derivedtypes.Union`

Their ir representation follows below.
"""
import typing

from .base import Documented, Entity, Named
from .datatypes import Typed


class Field(Entity, Named, Documented, Typed):
    """
    A representation of :class:`yace.ir.Struct` and
    :class:`yace.ir.Union`, utilized by compiler to emit code in the C API
    similar to::

        uint32_t bar;

    That is, within a ``struct/union`` block e.g.::

        struct foo {
            uint32_t bar;
        };

    The 'typ' and 'typ.width' members inherited from :class:`.Typed` are
    utilized to produce a fitting type-declaration for the target language, as
    in the examples above for C.
    """

    key: str = "field_decl"


class Bitfield(Field):
    """
    A representation of a bit-field within a :class:`yace.ir.Struct`
    or :class:`yace.ir.Union`, utilized by compiler to emit code in the C API similar
    to::

      uint32_t foo : 10;

    The 'typ' and 'typ.width' members inherited from :class:`.Typed` describe the type
    which in the example above it 'uint32_t'. The width of the bitfield is captured by
    the field "nbits"
    """

    key: str = "bitfield_decl"
    nbits: int


class Struct(Entity, Named, Documented):
    """
    A representation of a struct definition
    """

    key: str = "struct_decl"
    members: typing.List[Field | Bitfield]


class BitfieldStruct(Entity, Named, Documented):
    """
    A struct where all the fields / members are bitfields.

    A partitioning of a fixed-width datatype (such as uint32_t) into a subset of named
    bit-ranges. Commonly encapsualted in C struct. For example::

        struct bitfields {
            uint8_t foo : 2;
            uint8_t bar : 3;
            uint8_t baz : 3;
        }

    By doing so, then a struct-accessor is provided at less-than byte-addressability,
    which is very convenient. By providing a semanticly rich representation in **yace**
    then the actual implementation in a given language can be something better fitted.

    For example, the above code in C is not portable, whereas other languages might
    support portable representations. By providing the abstract bit-field, then the
    code-emitter can generate what is best-suited for a given language, rather than
    translating C-representation-idioms as the above into something sub-optimal.
    """

    key: str = "bitfield_struct_decl"
    width: int
    members: typing.List[Bitfield]

    def is_valid_members(self):
        """Checks whether the bitfield members match the width"""

        invalid_types = [type(m) for m in self.members if not isinstance(m, Bitfield)]
        if len(invalid_types):
            return (
                False,
                f"Invalid types in {self.sym}.members; "
                "expecting: Bits, got: [{invalid_types}]",
            )

        acc = sum([m.width for m in self.members])
        if acc != self.width:
            return (False, f"Aacumulated width({acc}) != {self.width}")

        return (True, None)


class Union(Struct):
    """Representation of enumerations / collections of constants"""

    key: str = "union_decl"
