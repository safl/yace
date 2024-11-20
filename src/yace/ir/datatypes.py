#!/usr/bin/env python3
"""
The **yace** data types consists of:

* No type: :class:`.Void`, :class:`.VoidPtr`

* Boolean: :class:`.Bool`

* Textual: :class:`.Char`

* Size types: :class:`.USize` / :class:`.ISize`

* Integers (Signed)

  * :class:`.I`, :class:`.I16`, :class:`.IShort`, :class:`.I8`
  * :class:`.ILongLong`, :class:`.I64`, :class:`.ILong`, :class:`.I32`

* Integers (Unsigned)

  * :class:`.U`, :class:`.U16`, :class:`.UShort`, :class:`.U8`
  * :class:`.ULongLong`, :class:`.U64`, :class:`.ULong`, :class:`.U32`

* Floating Point: :class:`.F32`, :class:`.F64`

Conventions
-----------

* A specialized Typespec should only update attribute-values, that is,
  not introduce new attributes

* A specialized Typespec should only set attributes which have values different
  than the default.

Their Yace IR follows below.
"""
import inspect
import sys
from typing import Literal, Optional, Union

from pydantic import BaseModel, root_validator

from .base import Entity


class Typespec(Entity):
    """
    All entities is-a :class:`.Entity`
    """

    canonical: str = ""

    void: bool = False  # Lack of type

    # Boolean and textual datatypes
    boolean: bool = False  # Boolean type, since C99: _Bool / true / false
    character: bool = False  # Character type, in C: char / 'k'

    # Numeral types
    size: bool = False  # Size-types; size_t, ssize_t
    integer: bool = False  # Integer types; int
    real: bool = False  # Floating point number e.g. float, double

    # Numerical types (Qualifiers and Modifiers)
    signed: bool = True  # Type-modifier for the integer datatype
    unsigned: bool = False  # Type-modifier for the integer datatype
    width: Optional[int] = None  # integer type width
    width_fixed: bool = False  # True: has an exact bit-width

    # Derived types
    union: bool = False  # union <id> { ... }
    struct: bool = False  # struct <id> { ... }
    enum: bool = False  #  enum <id> { ... }
    sym: Optional[str] = None  # symbol / tag of structs and unions

    # General Qualifiers and Modifiers
    const: bool = False  # Access-qualifier for all types:  'const'
    static: bool = False  # Storage-qualifier for all types: 'static'

    # Pointer attributes
    pointer: bool = False  # Pointer-type for all types: '*'
    pointee: Optional["Typespec"] = None

    # Array attributes
    array: bool = False  # Is an
    array_typ: Optional["Typespec"] = None
    array_length: int = 0  # This could also be a symbolic constant

    @root_validator(pre=True)
    def check_signage(cls, values):
        unsigned = values.get("unsigned")
        signed = values.get("signed")

        if unsigned is not None and signed is not None:
            if unsigned == signed:
                raise ValueError("unsigned and signed must have opposite values")
        elif unsigned is not None:
            values["signed"] = not unsigned
        elif signed is not None:
            values["unsigned"] = not signed

        return values

    def c_spelling(self):
        """
        Construct the C spelling
        This **should** produce the same as a concatenation of tokens.
        """

        spelling = []
        if self.const:
            spelling.append("const")

        if self.static:
            spelling.append("static")

        if self.void:
            spelling.append("void")
        elif self.boolean:
            spelling.append("bool")
        elif self.character:
            spelling.append("signed" if self.signed else "unsigned")
            spelling.append("char")
        elif self.size:
            spelling.append("ssize_t" if self.signed else "size_t")
        elif self.integer and self.width_fixed:
            if self.signed:
                spelling.append(f"int{self.width}_t")
            else:
                spelling.append(f"uint{self.width}_t")

        elif self.integer and not self.width_fixed:
            spelling.append("int")
        elif self.real:
            spelling.append("float")
        elif self.union:
            spelling.append(f"union {self.sym}")
        elif self.struct:
            spelling.append(f"struct {self.sym}")
        elif self.enum:
            spelling.append(f"enum {self.sym}")
        elif self.pointer:
            spelling.append(self.pointee.c_spelling())
            spelling.append("*")
        elif self.array:
            spelling.append(f"{self.array_typ.c_spelling()}")
            spelling.append(f"{self.sym}[{self.array_length}]")

        return " ".join(spelling)


class Pointer(Typespec):
    """Pointer"""

    key: str = "pointer_tspec"

    pointer: bool = True
    pointee: Typespec


class FunctionPointer(Typespec):
    """Function pointer"""

    key: str = "function_pointer_tspec"

    pointer: bool = True


class Array(Typespec):
    """Fixed-length arrays"""

    key: str = "array_tspec"

    array: bool = True
    array_typ: Typespec
    array_length: Optional[int]


class Record(Typespec):
    """Record; struct, union or enum"""

    key: str = "record_tspec"


class Enumeration(Typespec):
    """Elaborated / Enum / Enumeration"""

    key: str = "enum_tspec"


class Void(Typespec):
    """A void, that is, the type signaling no type"""

    key: str = "void_tspec"

    void: Optional[bool] = True


class VoidPtr(Typespec):
    """A void-pointer, that is, point to anything (including nothing)"""

    key: str = "void_pointer_tspec"

    void: Optional[bool] = True
    is_pointer: int = 1


class Char(Typespec):
    """
    A character; at least 8 bits wide.

    The C API emitter could produce::

        char

    for the :class:`.Char` entity.
    """

    key: str = "char_tspec"

    signed: bool = True
    unsigned: bool = False
    character: bool = True
    width: int = 8


class ISize(Typespec):
    """
    Signed Size-type

    The C API emitter could produce::

        ssize_t

    for the :class:`.ISize` entity.
    """

    key: str = "isize_tspec"

    signed: bool = True
    unsigned: bool = False
    size: bool = True
    width: Optional[int] = 16


class I8(Typespec):
    """
    Signed integer exactly 8 bits wide.

    A C emitter could for example produce::

        int8_t

    for the :class:`.I8` entity.
    """

    key: str = "i8_tspec"

    signed: bool = True
    unsigned: bool = False
    integer: bool = True
    width: int = 8
    width_fixed: bool = True


class IShort(Typespec):
    """
    Signed integer at least 8 bits wide.

    This is also known as a "short" int, as it is relative to "Int" shorter, typically,
    half the amount of bits.

    The C emitter can produce::

        short int

    for the :class:`.IHalf` entity.
    """

    key: str = "ih_tspec"

    signed: bool = True
    unsigned: bool = False
    integer: bool = True
    width: Optional[int] = 8


class I16(Typespec):
    """
    Signed integer exactly 16 bits wide.

    A C emitter could produce::

        int16_t

    for the :class:`.I16` entity.
    """

    key: str = "i16_tspec"

    signed: bool = True
    unsigned: bool = False
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

    key: str = "i_tspec"

    signed: bool = True
    unsigned: bool = False
    integer: bool = True
    width: int = 16


class I32(Typespec):
    """
    Signed integer exactly 32 bits wide.

    A C emitter could produce::

        int32_t

    for the :class:`.I32` entity.
    """

    key: str = "i32_tspec"

    signed: bool = True
    unsigned: bool = False
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

    key: str = "il_tspec"

    signed: bool = True
    unsigned: bool = False
    integer: bool = True
    width: Optional[int] = 32


class I64(Typespec):
    """
    Signed integer exactly 64 bits wide.

    A C emitter could produce::

        int64_t

    for the :class:`.I64` entity.
    """

    key: str = "i64_tspec"

    signed: bool = True
    unsigned: bool = False
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

    key: str = "ill_tspec"

    signed: bool = True
    unsigned: bool = False
    integer: bool = True
    width: Optional[int] = 64


class USize(Typespec):
    """
    Unsigned Size-type

    A C emitter could produce::

        size_t

    for the :class:`.USize` entity.
    """

    key: str = "usize_tspec"

    signed: bool = False
    unsigned: bool = True
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

    key: str = "u8_tspec"

    signed: bool = False
    unsigned: bool = True
    integer: bool = True
    width: Optional[int] = 8
    width_fixed: bool = True


class UShort(Typespec):
    """
    Unsigned integer at least 8 bits wide.

    This is also known as a "short" int, as it is relative to "Int" shorter, typically,
    half the amount of bits.

    A C emitter could produce::

        unsigned short int

    for the :class:`.UShort` entity.
    """

    key: str = "us_tspec"

    signed: bool = False
    unsigned: bool = True
    integer: bool = True
    width: Optional[int] = 8


class U16(Typespec):
    """
    Unsigned integer exactly 16 bits wide.

    A C emitter could produce::

        uint16_t

    for the :class:`.U16` entity.
    """

    key: str = "u16_tspec"

    signed: bool = False
    unsigned: bool = True
    integer: bool = True
    width: Optional[int] = 16
    width_fixed: bool = True


class U(Typespec):
    """
    Unsigned integer at least 16 bits wide.

    The C emitter can produce::

        unsigned int

    for the :class:`.U` entity.
    """

    key: str = "u_tspec"

    signed: bool = False
    unsigned: bool = True
    integer: bool = True
    width: Optional[int] = 16


class U32(Typespec):
    """
    Unsigned integer exactly 32 bits wide.

    A C emitter could produce::

        uint32_t

    for the :class:`.U32` entity.
    """

    key: str = "u32_tspec"

    signed: bool = False
    unsigned: bool = True
    integer: bool = True
    width: Optional[int] = 32
    width_fixed: bool = True


class ULong(Typespec):
    """
    Unsigned integer at least 32 bits wide.

    A C emitter could produce::

        unsigned long int

    for the :class:`.ULong` entity.
    """

    key: str = "ul_tspec"

    signed: bool = False
    unsigned: bool = True
    integer: bool = True
    width: Optional[int] = 32


class U64(Typespec):
    """
    Unsigned integer exactly 64 bits wide.

    A C emitter could produce::

        uint64_t

    for the :class:`.U64` entity.
    """

    key: str = "u64_tspec"

    signed: bool = False
    unsigned: bool = True
    integer: bool = True
    width: Optional[int] = 64
    width_fixed: bool = True


class ULongLong(Typespec):
    """
    Unsigned integer at least 64 bits wide.

    A C emitter could produce::

        unsigned long long int

    for the :class:`.ULongLong` entity.
    """

    key: str = "ull_tspec"

    signed: bool = False
    unsigned: bool = True
    integer: bool = True
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

    key: str = "f32_tspec"

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

    key: str = "f64_tspec"

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

    key: str = "bool_tspec"

    boolean: bool = True
    width: int = 8


class CString(Typespec):
    """
    A string pointer

    The C emitter produces::

        const char *

    for the :class:`.String` entity.
    """

    key: str = "string_tspec"

    pointer: bool = True
    pointee: Typespec = Char()
    const: bool = True


def classes():
    """Return all datatype classes"""

    return [
        cls
        for _, cls in inspect.getmembers(sys.modules[__name__])
        if inspect.isclass(cls) and issubclass(cls, Typespec) and not cls == Typespec
    ]


def get_shorthand_to_cls():
    return {cls.__fields__["key"].default: cls for cls in classes()}


def classes_shorthand_data():
    """Returns a map of shorthands to non-default datatype data"""

    default = Typespec(key="typespec").model_dump()  # Default typespec

    shorthands = {}  # Map to return
    for cls in classes():
        if cls.__fields__["key"].default in ["pointer_tspec", "array_tspec"]:
            continue

        data = cls().model_dump()  # Setup data

        for key, val in default.items():  # Remove default-values
            if key in data and data.get(key) == val and key not in ["key"]:
                del data[key]

        shorthands[data.get("key")] = data  # Add to shorthands

    return shorthands


# Create a Literal type from the list of strings
TypespecShorthand = Literal[
    tuple(sorted([cls.__fields__["key"].default for cls in classes()]))
]


class Typed(BaseModel):
    """
    Attribute-mixin; adding a reqried "has-a" relation to :class:`.Typespec`
    """

    typ: Union[Typespec, TypespecShorthand]
