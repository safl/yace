#!/usr/bin/env python3
"""
The **yace** data types consists of:

* Boolean:

  * :class:`.Bool`

* Numerical

  * Unsigned Integers: :class:`.Size`
  * Signed Integers: :class:`.Int`, :class:`.SizeSigned`

* Numerical -- Fixed Width

  * Unsigned Integers: :class:`.U8`, :class:`.U16`, :class:`.U32`, :class:`.U64`
  * Signed Integers: :class:`.I8`, :class:`.I16`, :class:`.I32`, :class:`.I64`
  * Floating Point: :class:`.F32`, :class:`.F64`

* Textual:

  * :class:`.Char`, :class:`.String`

Their idl representation follows below.
"""
import typing

from .base import Typespec


class I8(Typespec):
    """
    A basic data type: signed fixed-width integer; 8 bits wide.

    A C emitter could for example produce::

        int8_t

    for the :class:`I8` entity.
    """

    cls: str = "i8"
    integer: bool = True
    signed: bool = True
    width: int = 8


class I16(Typespec):
    """
    A basic data type: signed fixed-width integer; 16 bits wide.

    A C emitter could for example produce::

        int16_t

    for the :class:`I16` entity.
    """

    cls: str = "i16"
    integer: bool = True
    signed: bool = True
    width: int = 16


class I32(Typespec):
    """
    A basic data type: signed fixed-width integer; 32 bits wide.

    A C emitter could for example produce::

        int32_t

    for the :class:`I32` entity.
    """

    cls: str = "i32"
    integer: bool = True
    signed: bool = True
    width: int = 32


class I64(Typespec):
    """
    A basic data type: signed fixed-width integer; 64 bits wide.

    A C emitter could for example produce::

        int64_t

    for the :class:`I64` entity.
    """

    cls: str = "i64"
    integer: bool = True
    signed: bool = True
    width: int = 64


class U8(Typespec):
    """
    A basic data type: signed fixed-width integer; 8 bits wide.

    A C emitter could for example produce::

        uint8_t

    for the :class:`U8` entity.
    """

    cls: str = "u8"
    integer: bool = True
    signed: bool = False
    width: int = 8


class U16(Typespec):
    """
    A basic data type: signed fixed-width integer; 16 bits wide.

    A C emitter could for example produce::

        uint16_t

    for the :class:`U16` entity.
    """

    cls: str = "u16"
    integer: bool = True
    signed: bool = False
    width: int = 16


class U32(Typespec):
    """
    A basic data type: unsigned fixed-width integer; 32 bits wide.

    A C emitter could for example produce::

        uint32_t

    for the :class:`U32` entity.
    """

    cls: str = "u32"
    integer: bool = True
    signed: bool = False
    width: int = 32


class U64(Typespec):
    """
    A basic data type: unsigned fixed-width integer; 64 bits wide.

    A C emitter could for example produce::

        uint64_t

    for the :class:`U64` entity.
    """

    cls: str = "u64"
    integer: bool = True
    signed: bool = False
    width: int = 64


class F32(Typespec):
    """
    A floating point numerical value, possibly 32 bits wide

    The C emitter produces::

        float

    For the :class:`F32` entity.
    """

    cls: str = "f32"
    real: bool = True
    width: int = 32


class F64(Typespec):
    """
    A floating point numerical value, possibly 64 bits wide

    The C emitter produces::

        double

    For the :class:`F64` entity.
    """

    cls: str = "f64"
    real: bool = True
    width: int = 64


class Bool(Typespec):
    """
    A boolean, at least 8 bits wide, equivalent to the C99 "_Bool" and available
    as "bool" as defined by the standardized "stdbool.h" header.

    The C emitter produces::

        bool

    for the :class:`Bool` entity.
    """

    cls: str = "bool"
    boolean: bool = True
    width: int = 8


class Char(Typespec):
    """
    A character, at least 8 bits wide.

    The C API emitter could produce::

        char

    for the :class:`Char` entity.
    """

    cls: str = "char"
    character: bool = True
    width: int = 8


class Size(Typespec):
    """
    The C API emitter could produce::

        size_t

    for the :class:`Size` entity.
    """

    cls: str = "size"
    integer: bool = True
    signed: bool = True
    width: typing.Optional[int] = None


class SizeSigned(Typespec):
    """
    The C API emitter could produce::

        ssize_t

    for the :class:`SizeSigned` entity.
    """

    cls: str = "size"
    integer: bool = True
    width: typing.Optional[int] = None


class Int(Typespec):
    """
    The integer commonly used for error-handling, non-fixed width.

    The C emitter produces::

        int

    for the :class:`Int` entity.
    """

    cls: str = "int"
    integer: bool = True
    signed: bool = True
    width: typing.Optional[int] = None


class String(Typespec):
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
