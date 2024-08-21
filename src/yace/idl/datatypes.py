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
from typing import Literal, Optional, Union

from pydantic import BaseModel

from .base import Entity


class Typespec(Entity):
    """
    All entities is-a :class:`.Entity`
    """

    # Lack of type
    void: bool = False

    # Boolean and textual datatypes
    boolean: bool = False  # Boolean type, since C99: _Bool / true / false
    character: bool = False  # Character type, in C: char / 'k'

    # Numeral types
    size: bool = False  # Size-types; size_t, ssize_t
    integer: bool = False  # Integer types; int
    real: bool = False  # Floating point number e.g. float, double

    # Numerical types (Qualifiers and Modifiers)
    unsigned: bool = False  # Type-modifier for the integer datatype
    width: Optional[int] = None  # integer type width
    width_fixed: bool = False  # True: has an exact bit-width

    # Derived types
    union: bool = False  # union <id> { ... }
    struct: bool = False  # struct <id> { ... }
    sym: Optional[str] = None  # symbol / tag of structs and unions

    # General Qualifiers and Modifiers
    const: bool = False  # Access-qualifier for all types:  'const'
    static: bool = False  # Storage-qualifier for all types: 'static'
    pointer: int = 0  # Pointer-type for all types: '*'
    array: int = 0  # Array-type for all types: '[]'


class Void(Typespec):
    """A void, that is, the type signaling no type"""

    key: str = "void"

    void: Optional[bool] = True


class VoidPtr(Typespec):
    """A void-pointer, that is, point to anything (including nothing)"""

    key: str = "void_ptr"

    void: Optional[bool] = True
    pointer: int = 1


class Char(Typespec):
    """
    A character; at least 8 bits wide.

    The C API emitter could produce::

        char

    for the :class:`.Char` entity.
    """

    key: str = "char"

    character: bool = True
    width: int = 8


class ISize(Typespec):
    """
    Signed Size-type

    The C API emitter could produce::

        ssize_t

    for the :class:`.ISize` entity.
    """

    key: str = "isize"

    size: bool = True
    width: Optional[int] = 16


class I8(Typespec):
    """
    Signed integer exactly 8 bits wide.

    A C emitter could for example produce::

        int8_t

    for the :class:`.I8` entity.
    """

    key: str = "i8"

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

    key: str = "ih"

    integer: bool = True
    width: Optional[int] = 8


class I16(Typespec):
    """
    Signed integer exactly 16 bits wide.

    A C emitter could produce::

        int16_t

    for the :class:`.I16` entity.
    """

    key: str = "i16"

    integer: bool = True
    width: Optional[int] = 16
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

    key: str = "i"

    integer: bool = True
    width: Optional[int] = 16


class I32(Typespec):
    """
    Signed integer exactly 32 bits wide.

    A C emitter could produce::

        int32_t

    for the :class:`.I32` entity.
    """

    key: str = "i32"

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

    key: str = "il"

    integer: bool = True
    width: Optional[int] = 32


class I64(Typespec):
    """
    Signed integer exactly 64 bits wide.

    A C emitter could produce::

        int64_t

    for the :class:`.I64` entity.
    """

    key: str = "i64"

    integer: bool = True
    width: Optional[int] = 64
    width_fixed: bool = True


class ILongLong(Typespec):
    """
    Signed integer at least 64 bits wide.

    A C emitter could produce::

        long long int

    for the :class:`.ILongLong` entity.
    """

    key: str = "ill"

    integer: bool = True
    width: Optional[int] = 64


class USize(Typespec):
    """
    Unsigned Size-type

    A C emitter could produce::

        size_t

    for the :class:`.USize` entity.
    """

    key: str = "usize"

    size: bool = True
    unsigned: bool = True
    width: Optional[int] = 16


class U8(Typespec):
    """
    Unsigned integer exactly 8 bits wide.

    A C emitter could produce::

        uint8_t

    for the :class:`.U8` entity.
    """

    key: str = "u8"

    integer: bool = True
    unsigned: bool = True
    width: Optional[int] = 8
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

    key: str = "uh"

    integer: bool = True
    unsigned: bool = True
    width: Optional[int] = 8


class U16(Typespec):
    """
    Unsigned integer exactly 16 bits wide.

    A C emitter could produce::

        uint16_t

    for the :class:`.U16` entity.
    """

    key: str = "u16"

    integer: bool = True
    unsigned: bool = True
    width: Optional[int] = 16
    width_fixed: bool = True


class U(Typespec):
    """
    Unsigned integer at least 16 bits wide.

    The C emitter can produce::

        unsigned int

    for the :class:`.U` entity.
    """

    key: str = "u"

    integer: bool = True
    unsigned: bool = True
    width: Optional[int] = 16


class U32(Typespec):
    """
    Unsigned integer exactly 32 bits wide.

    A C emitter could produce::

        uint32_t

    for the :class:`.U32` entity.
    """

    key: str = "u32"

    integer: bool = True
    unsigned: bool = True
    width: Optional[int] = 32
    width_fixed: bool = True


class ULong(Typespec):
    """
    Unsigned integer at least 32 bits wide.

    A C emitter could produce::

        unsigned long int

    for the :class:`.ULong` entity.
    """

    key: str = "ul"

    integer: bool = True
    unsigned: bool = True
    width: Optional[int] = 32


class U64(Typespec):
    """
    Unsigned integer exactly 64 bits wide.

    A C emitter could produce::

        uint64_t

    for the :class:`.U64` entity.
    """

    key: str = "u64"

    integer: bool = True
    unsigned: bool = True
    width: Optional[int] = 64
    width_fixed: bool = True


class ULongLong(Typespec):
    """
    Unsigned integer at least 64 bits wide.

    A C emitter could produce::

        unsigned long long int

    for the :class:`.ULongLong` entity.
    """

    key: str = "ull"

    integer: bool = True
    unsigned: bool = True
    width: Optional[int] = 64


class F32(Typespec):
    """
    Floating point numerical value, possibly 32 bits wide

    The C language spec. does not define the width to be exact. However, we
    treat it as though it is, and error if it is not.

    A C emitter could produce::

        float

    for the :class:`.F32` entity.
    """

    key: str = "f32"

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

    key: str = "f64"

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

    key: str = "bool"

    boolean: bool = True
    width: int = 8


class String(Typespec):
    """
    A string pointer

    The C emitter produces::

        const char *

    for the :class:`.String` entity.
    """

    key: str = "string"

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

    default = Typespec(key="typespec").model_dump()  # Default typespec

    shorthands = {}  # Map to return
    for cls in classes():
        data = cls().model_dump()  # Setup data
        del data["lbl"]  # Remove "lbl"

        for key, val in default.items():  # Remove default-values
            if key in data and data.get(key) == val and key not in ["key"]:
                del data[key]

        shorthands[data.get("key")] = data  # Add to shorthands

    return shorthands


# Create a Literal type from the list of strings
TypespecShorthand = Literal[tuple(sorted([cls().key for cls in classes()]))]


class Typed(BaseModel):
    """
    Attribute-mixin; adding a reqried "has-a" relation to :class:`.Typespec`
    """

    typ: Union[Typespec, TypespecShorthand]
