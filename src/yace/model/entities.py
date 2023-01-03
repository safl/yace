#!/usr/bin/env python3
"""
Entities

Lorem ipsum dolor sit amet, consectetur adipiscing elit. Pellentesque malesuada
mauris gravida nibh sagittis, sit amet mollis risus luctus. Aliquam et commodo
leo.

Curabitur turpis lacus, consectetur sit amet massa et, porta blandit mi.
Aenean elementum eros tempor, gravida elit ac, faucibus mauris. Maecenas
commodo eleifend ante, nec vestibulum sem aliquam at.
"""
import yaml
import logging
import typing
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Entity:
    """Base class for entities containing common fields"""

    symbol: str


@dataclass
class Define(Entity):
    """
    Representation of simple MACROs / definitions

    When emitting the C API, the Define holds information to generate things
    like::

        #define MAX_SOMETHING 128

    The other code-emitters will generate similar globally scoped definitions.
    """

    val: int

    cls: str = "define"
    brief: typing.Optional[str] = None
    full: typing.Optional[str] = None


@dataclass
class Constant(Entity):
    """Represents the constant values in enumerations"""

    val: int
    fmt: str

    cls: str = "const"
    brief: typing.Optional[str] = None
    full: typing.Optional[str] = None


@dataclass
class Enumeration(Entity):
    """Representation of enumerations / collections of constants"""

    members: typing.List[Constant]

    cls: str = "enum"
    brief: typing.Optional[str] = None
    full: typing.Optional[str] = None


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

    dtype: str
    width: int
    fmt: str

    cls: str = "field"
    brief: typing.Optional[str] = None
    full: typing.Optional[str] = None
    val: typing.Optional[int] = None


@dataclass
class Bits(Entity):
    """Representation of enumerations / collections of constants"""

    width: int

    cls: str = "bits"
    brief: typing.Optional[str] = None
    full: typing.Optional[str] = None


@dataclass
class Bitfield(Entity):
    """Representation of enumerations / collections of constants"""

    members: typing.List[Bits]
    dtype: str
    width: int

    cls: str = "bitfield"
    brief: typing.Optional[str] = None
    full: typing.Optional[str] = None


@dataclass
class Struct(Entity):
    """Representation of enumerations / collections of constants"""

    members: typing.List

    cls: str = "struct"
    brief: typing.Optional[str] = None
    full: typing.Optional[str] = None


@dataclass
class Union(Entity):
    """Representation of enumerations / collections of constants"""

    members: typing.List

    cls: str = "union"
    brief: typing.Optional[str] = None
    full: typing.Optional[str] = None



