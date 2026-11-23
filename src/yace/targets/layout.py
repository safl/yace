# SPDX-FileCopyrightText: Simon A. F. Lund <os@safl.dk>
#
# SPDX-License-Identifier: GPL-2.0-only

"""
The position of each bit-field in the bytes of its record, for the printers of
Rust, Zig and Go, which keep a record of bit-fields as its bytes.

The IR records the offset of a bit-field in bits from the start of the record.
The bytes that hold the bit-field are read as an unsigned integer, least
significant byte first, and the bit-field is the 'width' bits from bit 'shift'
of that integer. GCC and Clang allocate bit-fields in this order on a
little-endian platform; the order on a big-endian platform is not read.
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
    """How C prints a bit-field of the resolved type 'typ'. A plain char has the
    signedness of the platform's char. An enum with a negative value is signed, because
    GCC and Clang then give it the type int"""

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
