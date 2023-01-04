#!/usr/bin/env python3
"""
This module contains bla blaClasses inheriting from this type include data
types with known and fixed storage

* Boolean

  * :class:`.Bool`

* Numerical

  * Unsigned Integers: :class:`.U8`, :class:`.U16`, :class:`.U32`, :class:`.U64`
  * Signed Integers: :class:`.I8`, :class:`.I16`, :class:`.I32`, :class:`.I64`
  * Floating Point: :class:`.F32`, :class:`.F64`

* Textual

  * :class:`.Char`
  * :class:`.String`

"""
import typing
from dataclasses import dataclass, field

from .entities import Typedecl


@dataclass
class Datatype(Typedecl):
    """
    These types should have a known and well-defined storage-width, e.g. an
    unsigned 32-bit integer should consume 4 bytes of memory. Modifiers are
    available:
    """

    width: int = 8


@dataclass
class I8(Typedecl):
    """
    A signed integer, 8 bits wide.

    The C emitter produces::

        int8_t

    for the :class:`I64` entity.
    """

    cls: str = "i8"
    width: int = 8


@dataclass
class I16(Typedecl):
    """
    A signed integer, 16 bits wide.

    The C emitter produces::

        int16_t

    for the :class:`I16` entity.
    """

    cls: str = "i16"
    width: int = 16


@dataclass
class I32(Typedecl):
    """
    A signed integer, 32 bits wide.

    The C emitter produces::

        int32_t

    for the :class:`I32` entity.
    """

    cls: str = "i32"
    width: int = 32


@dataclass
class I64(Typedecl):
    """
    A signed integer, 64 bits wide.

    The C emitter produces::

        int64_t

    for the :class:`I64` entity.
    """

    cls: str = "i64"
    width: int = 64


@dataclass
class U8(Typedecl):
    """
    A unsigned integer, 8 bits wide.

    The C emitter produces::

        uint8_t

    for the :class:`U8` entity.
    """

    cls: str = "u8"
    width: int = 8


@dataclass
class U16(Typedecl):
    """
    A unsigned integer, 16 bits wide".

    The C emitter produces::

        uint16_t

    for the :class:`U16` entity.
    """

    cls: str = "u16"
    width: int = 16


@dataclass
class U32(Typedecl):
    """
    An unsigned integer, 32 bits wide.

    The C emitter produces::

        uint32_t

    for the :class:`U32` entity.
    """

    cls: str = "u32"
    width: int = 32


@dataclass
class U64(Typedecl):
    """
    A unsigned integer, 64 bits wide.

    The C emitter produces::

        uint64_t

    for the :class:`U64` entity.
    """

    cls: str = "u64"
    width: int = 64


@dataclass
class F32(Typedecl):
    """
    A floating point numerical value, possibly 32 bits wide

    The C emitter produces::

        float

    For the :class:`F32` entity.
    """

    cls: str = "f32"
    width: int = 32


@dataclass
class F64(Typedecl):
    """
    A floating point numerical value, possibly 64 bits wide

    The C emitter produces::

        double

    For the :class:`F64` entity.
    """

    cls: str = "f64"
    width: int = 64


@dataclass
class Bool(Typedecl):
    """
    A boolean, at least 8 bits wide, equivalent to the C99 "_Bool" and available
    as "bool" as defined by the standardized "stdbool.h" header.

    The C emitter produces::

        bool

    for the :class:`Bool` entity.
    """

    cls: str = "bool"
    width: int = 8


@dataclass
class Char(Typedecl):
    """
    A character, at least 8 bits wide.

    The C emitter produces::

        char

    for the :class:`Char` entity.
    """

    cls: str = "char"
    width: int = 8


@dataclass
class String(Typedecl):
    """
    A string pointer

    The C emitter produces::

        const char *

    for the :class:`String` entity.
    """

    cls: str = "string"
    width: int = 8
    pointer: int = 1
    const: bool = True
