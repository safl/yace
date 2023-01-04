#!/usr/bin/env python3
"""
Entities are the base classes representing the language constructs of C APIs in
the :class:`yace.model.interface.InterfaceModel`. The entities serve as
encapsulated type-checking of YAML-definitions of the language model.
"""
import typing
from dataclasses import dataclass, field

from .entities import Entity, Typedecl


@dataclass
class Bits(Entity):
    """Representation of a :class:`.Bitfield` member."""

    width: int

    cls: str = "bits"


@dataclass
class Bitfield(Entity):
    """Representation of enumerations / collections of constants"""

    members: typing.List[Bits]
    dtype: Typedecl

    cls: str = "bitfield"


@dataclass
class Field(Entity):
    """
    :class:`.Field` represents members of :class:`.Struct` and :class:`.Union`,
    utilized by compiler to emit code in the C API similar to::

        uint32_t bar;

    That is, within a ``struct/union`` block e.g.::

        struct foo {
            uint32_t bar;
        };

    The 'dtype' and 'width' members are utilized to produce a fitting
    type-declaration for the target language, as in the examples above for C.
    """

    dtype: Typedecl
    cls: str = "field"
    fmt: str = "%u"


@dataclass
class Struct(Entity):
    """Representation of enumerations / collections of constants"""

    members: typing.List

    cls: str = "struct"
