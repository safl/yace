#!/usr/bin/env python3
"""
The **yace** data types consists of:

* No type: :class:`.Void`, :class:`.VoidPtr`

* Boolean: :class:`.Bool`

* Textual: :class:`.Char`

* Size types: :class:`.USize` / :class:`.ISize`

* Integers (Signed)

  * :class:`.I`, :class:`.I16`, :class:`.IHalf`, :class:`.I8`
  * :class:`.ILongLong`, :class:`.I64`, :class:`.ILong`, :class:`.I32`

* Integers (Unsigned)

  * :class:`.U`, :class:`.U16`, :class:`.UHalf`, :class:`.U8`
  * :class:`.ULongLong`, :class:`.U64`, :class:`.ULong`, :class:`.U32`

* Floating Point: :class:`.F32`, :class:`.F64`

Conventions
-----------

* A specialized Typespec should only update attribute-values, that is,
  not introduce new attributes

* A specialized Typespec should only set attributes which have values different
  than the default.

Their idl representation follows below.
"""
import inspect
import sys
import typing

from .base import Typespec


class Void(Typespec):
    """A void, that is, the type signaling no type"""

    cls: str = "void"

    void: typing.Optional[bool] = True


class VoidPtr(Typespec):
    """A void-pointer, that is, point to anything (including nothing)"""

    cls: str = "void_ptr"

    void: typing.Optional[bool] = True
    pointer: int = 1


class Char(Typespec):
    """
    A character; at least 8 bits wide.

    The C API emitter could produce::

        char

    for the :class:`.Char` entity.
    """

    cls: str = "char"

    character: bool = True
    width: int = 8


class ISize(Typespec):
    """
    Signed Size-type

    The C API emitter could produce::

        ssize_t

    for the :class:`.ISize` entity.
    """

    cls: str = "isize"

    size: bool = True
    width: typing.Optional[int] = 16


class I8(Typespec):
    """
    Signed integer exactly 8 bits wide.

    A C emitter could for example produce::

        int8_t

    for the :class:`.I8` entity.
    """

    cls: str = "i8"

    integer: bool = True
    width: int = 8
    width_fixed: bool = True


class IHalf(Typespec):
    """
    Signed integer at least 8 bits wide.

    This is also known as "half" or "short" int, as it is relative to "Int"
    shorter, typically, half the amount of bits.

    The C emitter can produce::

        short int

    for the :class:`.IHalf` entity.
    """

    cls: str = "ih"

    integer: bool = True
    width: typing.Optional[int] = 8


class I16(Typespec):
    """
    Signed integer exactly 16 bits wide.

    A C emitter could produce::

        int16_t

    for the :class:`.I16` entity.
    """

    cls: str = "i16"

    integer: bool = True
    width: typing.Optional[int] = 16
    width_fixed: bool = True


class I(Typespec):
    """
    Signed integer at least 16 bits wide.

    Historically, the int matched the bit-width of the processor when C came
    out in the early days on "ANSI" C / K&R. That is, 16bit processors.

    Thus, the short/long/long/long are "modifiers" of this base-type, although
    the width on a 64bit system today is often 32bit for this type.

    The C emitter can produce::

        int

    for the :class:`.I` entity.
    """

    cls: str = "i"

    integer: bool = True
    width: typing.Optional[int] = 16


class I32(Typespec):
    """
    Signed integer exactly 32 bits wide.

    A C emitter could produce::

        int32_t

    for the :class:`.I32` entity.
    """

    cls: str = "i32"

    integer: bool = True
    width: int = 32
    width_fixed: bool = True


class ILong(Typespec):
    """
    Signed integer at least 32 bits wide.

    The C emitter produces::

        long int

    for the :class:`.ILong` entity.
    """

    cls: str = "il"

    integer: bool = True
    width: typing.Optional[int] = 32


class I64(Typespec):
    """
    Signed integer exactly 64 bits wide.

    A C emitter could produce::

        int64_t

    for the :class:`.I64` entity.
    """

    cls: str = "i64"

    integer: bool = True
    width: typing.Optional[int] = 64
    width_fixed: bool = True


class ILongLong(Typespec):
    """
    Signed integer at least 64 bits wide.

    A C emitter could produce::

        long long int

    for the :class:`.ILongLong` entity.
    """

    cls: str = "ill"

    integer: bool = True
    width: typing.Optional[int] = 64


class USize(Typespec):
    """
    Unsigned Size-type

    A C emitter could produce::

        size_t

    for the :class:`.USize` entity.
    """

    cls: str = "usize"

    size: bool = True
    unsigned: bool = True
    width: typing.Optional[int] = 16


class U8(Typespec):
    """
    Unsigned integer exactly 8 bits wide.

    A C emitter could produce::

        uint8_t

    for the :class:`.U8` entity.
    """

    cls: str = "u8"

    integer: bool = True
    unsigned: bool = True
    width: typing.Optional[int] = 8
    width_fixed: bool = True


class UHalf(Typespec):
    """
    Unsigned integer at least 8 bits wide.

    This is also known as "half" or "short" int, as it is relative to "Int"
    shorter, typically, half the amount of bits.

    A C emitter could produce::

        unsigned short int

    for the :class:`.UHalf` entity.
    """

    cls: str = "uh"

    integer: bool = True
    unsigned: bool = True
    width: typing.Optional[int] = 8


class U16(Typespec):
    """
    Unsigned integer exactly 16 bits wide.

    A C emitter could produce::

        uint16_t

    for the :class:`.U16` entity.
    """

    cls: str = "u16"

    integer: bool = True
    unsigned: bool = True
    width: typing.Optional[int] = 16
    width_fixed: bool = True


class U(Typespec):
    """
    Unsigned integer at least 16 bits wide.

    The C emitter can produce::

        unsigned int

    for the :class:`.U` entity.
    """

    cls: str = "u"

    integer: bool = True
    unsigned: bool = True
    width: typing.Optional[int] = 16


class U32(Typespec):
    """
    Unsigned integer exactly 32 bits wide.

    A C emitter could produce::

        uint32_t

    for the :class:`.U32` entity.
    """

    cls: str = "u32"

    integer: bool = True
    unsigned: bool = True
    width: typing.Optional[int] = 32
    width_fixed: bool = True


class ULong(Typespec):
    """
    Unsigned integer at least 32 bits wide.

    A C emitter could produce::

        unsigned long int

    for the :class:`.ULong` entity.
    """

    cls: str = "ul"

    integer: bool = True
    unsigned: bool = True
    width: typing.Optional[int] = 32


class U64(Typespec):
    """
    Unsigned integer exactly 64 bits wide.

    A C emitter could produce::

        uint64_t

    for the :class:`.U64` entity.
    """

    cls: str = "u64"

    integer: bool = True
    unsigned: bool = True
    width: typing.Optional[int] = 64
    width_fixed: bool = True


class ULongLong(Typespec):
    """
    Unsigned integer at least 64 bits wide.

    A C emitter could produce::

        unsigned long long int

    for the :class:`.ULongLong` entity.
    """

    cls: str = "ull"

    integer: bool = True
    unsigned: bool = True
    width: typing.Optional[int] = 64


class F32(Typespec):
    """
    Floating point numerical value, possibly 32 bits wide

    The C language spec. does not define the width to be exact. However, we
    treat it as though it is, and error if it is not.

    A C emitter could produce::

        float

    for the :class:`.F32` entity.
    """

    cls: str = "f32"

    real: bool = True
    width: int = 32
    width_fixed: bool = True


class F64(Typespec):
    """
    Floating point numerical value, possibly 64 bits wide

    The C language spec. does not define the width to be exact. However, we
    treat it as though it is, and error if it is not.

    A C emitter could produce::

        double

    for the :class:`.F64` entity.
    """

    cls: str = "f64"

    real: bool = True
    width: int = 64


class Bool(Typespec):
    """
    A boolean, at least 8 bits wide

    Equivalent to the C99 "_Bool" and available
    as "bool" as defined by the standardized "stdbool.h" header.

    A C emitter could produce::

        # In C99
        _Bool

    Or, using ``<stdbool.h>``::

        bool

    for the :class:`.Bool` entity.
    """

    cls: str = "bool"

    boolean: bool = True
    width: int = 8


class String(Typespec):
    """
    A string pointer

    The C emitter produces::

        const char *

    for the :class:`.String` entity.
    """

    cls: str = "string"

    character: bool = True
    pointer: int = 1
    const: bool = True


def classes():
    """Return all datatype classes"""

    return [
        cls
        for _, cls in inspect.getmembers(sys.modules[__name__])
        if inspect.isclass(cls) and issubclass(cls, Typespec) and not cls == Typespec
    ]


def classes_shorthand_data():
    """Returns a map of shorthands to non-default datatype data"""

    default = Typespec({"cls": "typespec"}).as_dict()  # Default typespec

    shorthands = {}  # Map to return
    for cls in classes():
        data = cls().as_dict()  # Setup data
        del data["lbl"]  # Remove "lbl"

        for key, val in default.items():  # Remove default-values
            if key in data and data.get(key) == val and key not in ["cls"]:
                del data[key]

        shorthands[cls.cls] = data  # Add to shorthands

    return shorthands
