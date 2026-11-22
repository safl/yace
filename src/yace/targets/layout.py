# SPDX-FileCopyrightText: Simon A. F. Lund <os@safl.dk>
#
# SPDX-License-Identifier: GPL-2.0-only

"""
Where the targets that keep a record of bit-fields as its bytes, Rust, Zig and
Go, read each bit-field from, for their printers to print it as C does.

The IR records the offset of a bit-field in bits from the start of the record,
as libclang gives it. The bytes holding the bit-field are read as an unsigned
integer of the least significant byte first, and the bit-field is the 'width'
bits from bit 'shift' of it: the order in which GCC and Clang allocate
bit-fields on a little-endian platform, as x86-64 and AArch64 are. On a
big-endian one, they allocate them from the most significant bit, which this
does not read.
"""

from typing import Dict, NamedTuple, Optional

from yace.ir import decls, types
from yace.ir.semantics import SIGNED


class BitField(NamedTuple):
    first: int  # the byte of the record its lowest bit is in
    nbytes: int  # the bytes, from 'first', that hold it
    shift: int  # the bits of byte 'first' below it
    width: int
    kind: str  # how C prints it: "bool", "signed", "unsigned" or "char"


def kind(typ, enums: Dict[str, decls.Enum]) -> str:
    """How C prints a bit-field of the resolved type 'typ': a plain char is as
    signed as the platform's char; an enum is signed where it has a negative
    value, as GCC and Clang then make its type int, and unsigned int else"""

    if isinstance(typ, types.EnumRef):
        enum = enums.get(typ.name)
        if enum is None:
            return "signed"
        if enum.underlying is not None:
            return kind(enum.underlying, enums)
        return "signed" if any(m.value < 0 for m in enum.members) else "unsigned"
    name = getattr(typ, "name", "")
    if name == "bool":
        return "bool"
    if name == "char":
        return "char"
    return "signed" if name in SIGNED else "unsigned"


def bitfield(field: decls.Field, typ, enums) -> Optional[BitField]:
    """Where 'field', a bit-field of the resolved type 'typ', is in the bytes
    of its record, or None where it is not a bit-field or has no offset"""

    if field.bits is None or field.offset is None or not field.bits:
        return None
    first, shift = divmod(field.offset, 8)
    nbytes = (shift + field.bits + 7) // 8
    return BitField(first, nbytes, shift, field.bits, kind(typ, enums))
