"""
Fields of bits: an integer field of a record and the masks naming its parts

The C subset has no bit-fields. A field of bits is an unsigned integer, and each
of its parts is named by a mask, an object-like ``#define`` of the part's bits
in their place. Both ends of the link are written in the header, in the doc
comments, and **yace** checks that they agree:

* the integer names the prefix of its masks: ``///< <what>, see
  <PREFIX>_<STRUCT>_<FIELD>_*``
* each mask is named by that prefix and the part, and says which bits of which
  field it is: ``/** <what>; bits <hi>:<lo> of '<field>' */``, or ``bit <n>``
  for one bit

For example::

  struct foo_status {
	uint16_t code; ///< Status code, see FOO_STATUS_CODE_*
  };

  /** Generic, command specific or media error; bits 2:0 of 'code' */
  #define FOO_STATUS_CODE_TYPE 0x7
  /** Whether more is in the log; bit 15 of 'code' */
  #define FOO_STATUS_CODE_MORE 0x8000

links the parts ``type`` and ``more`` to ``code`` of ``struct foo_status``, as
:class:`yace.ir.decls.Mask` on the field. Nothing is inferred from a name
alone: a ``#define`` is a mask when its doc says which bits it is, and it
belongs to the field whose doc names its prefix. Every disagreement is reported
by the bit-mask rule, and the mask is not linked. A field whose ``see
<PREFIX>_*`` names no masks, such as one naming the constants of its values,
is not a field of bits.
"""

import ctypes
import re
from typing import Callable, Dict, List, Optional, Tuple

from . import decls, types

# Where a mask's doc says which bits it is, at the end of the doc
LOCATION = re.compile(
    r"(?:^|;)\s*(?P<form>bits?)\s+(?P<hi>\d+)(?::(?P<lo>\d+))?\s+of\s+'(?P<field>\w+)'"
    r"\s*\.?\s*$"
)
# Where an integer field's doc names the prefix of its masks
PREFIX = re.compile(r"\bsee\s+([A-Za-z_]\w*?)_\*")

# The name the pretty-printers print the value of the whole field by
VALUE_KEY = "val"

CTYPES = {
    "unsigned char": ctypes.c_ubyte,
    "unsigned short": ctypes.c_ushort,
    "unsigned int": ctypes.c_uint,
    "unsigned long": ctypes.c_ulong,
    "unsigned long long": ctypes.c_ulonglong,
    "uint8_t": ctypes.c_uint8,
    "uint16_t": ctypes.c_uint16,
    "uint32_t": ctypes.c_uint32,
    "uint64_t": ctypes.c_uint64,
    "uintptr_t": ctypes.c_size_t,
    "size_t": ctypes.c_size_t,
}


def width_of(typ) -> Optional[int]:
    """The bits of 'typ', when it is an unsigned integer"""

    if isinstance(typ, types.Builtin) and typ.name in CTYPES:
        return 8 * ctypes.sizeof(CTYPES[typ.name])
    return None


def location(doc) -> Optional[re.Match]:
    """Where the doc of a mask says which bits it is: the end of its last
    paragraph"""

    paragraphs = [doc.brief] + [p for p in doc.description.split("\n\n") if p]
    return LOCATION.search(paragraphs[-1]) if paragraphs[-1] else None


def link(entities: list, report: Callable[[str, str, object], None], cursors: dict):
    """Link each mask among the #defines of 'entities' to its field"""

    def problem(define: decls.Define, message: str):
        report("bit-mask", f"'{define.name}' {message}", cursors.get(define.name))

    # The prefix each integer field names, with the record and the field
    owners: Dict[str, List[Tuple[object, decls.Field]]] = {}
    for record in (e for e in entities if isinstance(e, decls.RECORDS)):
        for field in record.fields:
            text = f"{field.doc.brief} {field.doc.description}"
            for prefix in dict.fromkeys(PREFIX.findall(text)):
                owners.setdefault(prefix, []).append((record, field))

    defines = list(
        {
            e.name: e
            for e in reversed(entities)
            if isinstance(e, decls.Define) and isinstance(e.value, decls.IntLiteral)
        }.values()
    )[::-1]
    masked: Dict[int, list] = {}  # id of a field, its masks with their #define
    for define in defines:
        found = location(define.doc)
        if found is None:
            continue
        name = found["field"]
        under = [
            (prefix, record, field)
            for prefix, fields in owners.items()
            if define.name.startswith(f"{prefix}_")
            for record, field in fields
        ]
        candidates = [entry for entry in under if entry[2].name == name]
        if not candidates:
            if under:
                others = ", ".join(
                    sorted({f"'{r.name}.{f.name}'" for _, r, f in under})
                )
                problem(
                    define,
                    f"says it is of '{name}', but its name puts it under {others}",
                )
            else:
                problem(
                    define,
                    f"says it is of '{name}', but no field documents its masks as"
                    " 'see <PREFIX>_*' with a prefix of the name",
                )
            continue
        longest = max(len(prefix) for prefix, _, _ in candidates)
        candidates = [entry for entry in candidates if len(entry[0]) == longest]
        if len(candidates) > 1:
            fields = ", ".join(f"'{r.name}.{f.name}'" for _, r, f in candidates)
            problem(define, f"is under the masks of each of {fields}")
            continue
        prefix, record, field = candidates[0]

        part = define.name[len(prefix) + 1 :].lower()
        if not re.fullmatch(r"[a-z_][a-z0-9_]*", part):
            problem(define, f"names the part '{part}', which is no identifier")
            continue
        if part == VALUE_KEY:
            problem(
                define,
                f"names the part '{part}', which the pretty-printers print the"
                f" value of '{field.name}' as",
            )
            continue
        upper = prefix.upper()
        if upper != field.name.upper() and not upper.endswith(f"_{field.name.upper()}"):
            problem(
                define,
                f"is under '{prefix}_*', which does not end in the name of"
                f" '{record.name}.{field.name}'",
            )
            continue
        bits = width_of(field.typ)
        if bits is None:
            problem(
                define,
                f"is of bits of '{record.name}.{field.name}', which is not an"
                " unsigned integer",
            )
            continue

        value = define.value.value
        if value <= 0:
            problem(define, f"is {value}, which masks no bits")
            continue
        lo = (value & -value).bit_length() - 1
        run = value >> lo
        if run & (run + 1):
            problem(define, f"is {value:#x}, whose bits are not contiguous")
            continue
        width = run.bit_length()
        hi = lo + width - 1
        if hi >= bits:
            problem(
                define,
                f"is {value:#x}, wider than '{record.name}.{field.name}', of"
                f" {bits} bits",
            )
            continue

        said = (int(found["hi"]), int(found["lo"] if found["lo"] else found["hi"]))
        where = f"bit {lo}" if width == 1 else f"bits {hi}:{lo}"
        if said != (hi, lo) or (found["form"] == "bit") != (width == 1):
            problem(
                define,
                f"is {value:#x}, {where} of '{field.name}', but its doc says"
                f" '{found[0].strip(' ;.')}'",
            )
            continue

        taken = masked.setdefault(id(field), [])
        overlaps = [d for mask, d in taken if mask.value & value]
        if overlaps:
            problem(define, f"overlaps '{overlaps[0].name}' in '{field.name}'")
            continue
        taken.append(
            (
                decls.Mask(
                    name=part, define=define.name, lo=lo, width=width, doc=define.doc
                ),
                define,
            )
        )

    linked = {id(f): f for fields in owners.values() for _, f in fields}
    for key, found in masked.items():
        linked[key].masks = sorted((mask for mask, _ in found), key=lambda m: m.lo)

    unlocated(defines, owners, masked, problem)
    accessors(entities, cursors, report)


def unlocated(defines, owners, masked, problem):
    """Report a #define under the prefix of a field of bits that does not say
    which bits it is, such as one whose doc has the bits misspelled"""

    for define in defines:
        if location(define.doc) is not None:
            continue
        for prefix, fields in owners.items():
            if not define.name.startswith(f"{prefix}_"):
                continue
            for record, field in fields:
                if id(field) in masked:
                    problem(
                        define,
                        f"is under the masks of '{record.name}.{field.name}', but"
                        " its doc does not end in 'bits <hi>:<lo> of"
                        f" '{field.name}'' or 'bit <n> of '{field.name}''",
                    )


def accessors(entities, cursors, report):
    """Unlink the masks whose accessor, '<field>_<part>', is named as a field
    or another accessor of the record; the targets name them so"""

    for record in (e for e in entities if isinstance(e, decls.RECORDS)):
        names = {field.name for field in record.fields}
        for field in record.fields:
            kept = []
            for mask in field.masks:
                name = f"{field.name}_{mask.name}"
                if name in names:
                    report(
                        "bit-mask",
                        f"'{mask.define}' is read as '{name}', which"
                        f" '{record.name}' has already",
                        cursors.get(mask.define),
                    )
                    continue
                names.add(name)
                kept.append(mask)
            field.masks = kept
