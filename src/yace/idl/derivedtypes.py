#!/usr/bin/env python3
"""
The **yace** derived types consists of:

* :class:`yace.idl.derivedtypes.Struct` with :class:`.Field` members

* :class:`yace.idl.derivedtypes.Bitfield` with :class:`.Bits` members

* :class:`yace.idl.derivedtypes.Union`

Their idl representation follows below.
"""
import typing

from .base import Documented, Entity, Named, Typed


class Bits(Entity, Named, Documented):
    """Representation of a :class:`.Bitfield` member."""

    cls: str = "bits"
    width: int


class Bitfield(Entity, Named, Documented):
    """
    Representation of a bitfield, that is a partitioning of a fixed-width
    datatype (such as uint32_t) into a subset of named bit-ranges. Commonly
    encapsualted in C struct. For example::

        struct {
            uint8_t foo : 2;
            uint8_t bar : 3;
            uint8_t baz : 3;
        }

    By doing so, then a struct-accessor is provided at less-than
    byte-addressability, which is very convenient. By providing a semanticly
    rich representation in **yace** then the actual implementation in a given
    language can be something better fitted.

    For example, the above code in C is not portable, whereas other languages
    might support portable representations. By providing the abstract
    bit-field, then the code-emitter can generate what is best-suited for a
    given language, rather than translating C-representation-idioms as the
    above into something sub-optimal.
    """

    cls: str = "bitfield"
    width: int
    members: typing.List[Bits]

    def is_valid_members(self):
        """Checks whether the bitfield members match the width"""

        invalid_types = [type(m) for m in self.members if not isinstance(m, Bits)]
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


class Field(Entity, Named, Documented, Typed):
    """
    A representation of :class:`yace.idl.Struct` and
    :class:`yace.idl.Union`, utilized by compiler to emit code in the C API
    similar to::

        uint32_t bar;

    That is, within a ``struct/union`` block e.g.::

        struct foo {
            uint32_t bar;
        };

    The 'typ' and 'typ.width' members inherited from :class:`.Typed` are
    utilized to produce a fitting type-declaration for the target language, as
    in the examples above for C.

    The 'fmt' attribute provides a format-char/string for a code-emitter to
    utlize when emitting a pretty-printer.
    """

    cls: str = "field"
    fmt: str


class Struct(Entity, Named, Documented):
    """
    A representation of a struct definition
    """

    cls: str = "struct"
    members: typing.List[Field]


class Union(Struct):
    """Representation of enumerations / collections of constants"""

    cls: str = "union"
