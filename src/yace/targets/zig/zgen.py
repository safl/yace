# SPDX-FileCopyrightText: Simon A. F. Lund <os@safl.dk>
#
# SPDX-License-Identifier: GPL-2.0-only

"""
zgen produces the Zig code that depends on the IR: names, the Zig type of each
IR type, and the statements of the pretty-printers. The raw layer uses the
types of Zig's own translation of C: a C pointer, ``[*c]T``, which may be NULL,
and an optional pointer to an opaque type or a function.
"""

import re
from typing import Dict, List

from yace.ir import decls, types
from yace.ir.masks import VALUE_KEY
from yace.ir.model import Model
from yace.targets.capi.target import string_literal
from yace.targets.layout import bitfield
from yace.targets.python.pygen import camel

ZIG_TYPES = {
    "bool": "bool",
    "char": "u8",
    "signed char": "i8",
    "unsigned char": "u8",
    "short": "c_short",
    "unsigned short": "c_ushort",
    "int": "c_int",
    "unsigned int": "c_uint",
    "long": "c_long",
    "unsigned long": "c_ulong",
    "long long": "c_longlong",
    "unsigned long long": "c_ulonglong",
    "float": "f32",
    "double": "f64",
    "int8_t": "i8",
    "int16_t": "i16",
    "int32_t": "i32",
    "int64_t": "i64",
    "uint8_t": "u8",
    "uint16_t": "u16",
    "uint32_t": "u32",
    "uint64_t": "u64",
    "intptr_t": "isize",
    "uintptr_t": "usize",
    "size_t": "usize",
    "ssize_t": "isize",
    "ptrdiff_t": "isize",
}

KEYWORDS = set(
    "addrspace align allowzero and anyframe anytype asm break callconv catch"
    " comptime const continue defer else enum errdefer error export extern fn for"
    " if inline linksection noalias noinline nosuspend opaque or orelse packed pub"
    " resume return struct suspend switch test threadlocal try union unreachable"
    " var volatile while bool void type true false null undefined".split()
)


def ident(name: str) -> str:
    """Return 'name', escaped for Zig"""

    return f'@"{name}"' if name in KEYWORDS else name


def lower_camel(name: str) -> str:
    """Return 'name' in camelCase"""

    text = camel(name)
    return ident(text[:1].lower() + text[1:]) if text else name


def doc_lines(doc, errors: str = "") -> List[str]:
    """Return 'doc' as the lines of a doc comment, without the '///'; 'errors'
    says when the function fails"""

    lines = []
    if doc.brief:
        lines.append(doc.brief)
    for para in [p for p in doc.description.split("\n\n") if p]:
        lines += [""] + para.splitlines()
    for line in doc.prose():
        lines += ["", line]
    if doc.params:
        lines += ["", "Parameters:", ""]
        lines += [f"* `{name}`: {text}" for name, text in doc.params.items()]
    if doc.returns:
        lines += ["", f"Returns {doc.returns}"]
    if errors:
        lines += ["", f"Errors: {errors}"]
    return lines


class Namer(object):
    """Maps the C name of a type to its Zig name: CamelCase, or the C name
    where two would share one"""

    def __init__(self, model: Model):
        self.records = model.records()
        self.typedefs = model.typedefs()
        self.enums = model.enums()
        self.stubs: Dict[str, str] = {}

        self.aliases = {
            name
            for name, typedef in self.typedefs.items()
            if isinstance(typedef.typ, (types.Record, types.EnumRef))
            and typedef.typ.name == name
        }
        wanted: Dict[str, List[str]] = {}
        named = [*self.records, *self.enums]
        for name in named + [t for t in self.typedefs if t not in self.aliases]:
            wanted.setdefault(camel(name), []).append(name)
        self.names = {}
        for zig, cnames in wanted.items():
            for cname in cnames:
                self.names[cname] = ident(zig if len(cnames) == 1 else cname)

    def __call__(self, cname: str) -> str:
        if cname in self.names:
            return self.names[cname]
        if cname not in self.stubs:
            self.stubs[cname] = ident(camel(cname) or cname)
        return self.stubs[cname]

    def resolve(self, typ):
        while isinstance(typ, types.TypedefRef) and typ.name in self.typedefs:
            typ = self.typedefs[typ.name].typ
        return typ

    def is_opaque(self, typ) -> bool:
        """Return whether Zig knows 'typ' only as opaque"""

        if isinstance(typ, types.Builtin):
            return typ.name == "void"
        if isinstance(typ, types.Record):
            record = self.records.get(typ.name)
            return record is None or (not record.fields and record.size is None)
        if isinstance(typ, types.TypedefRef):
            if typ.name in self.typedefs:
                return self.is_opaque(self.resolve(typ))
            return True
        return False

    def ztype(self, typ, param: bool = False) -> str:
        """Return the Zig type of 'typ'; with 'param', an array is a pointer"""

        if isinstance(typ, types.Builtin):
            return "void" if typ.name == "void" else ZIG_TYPES[typ.name]

        if isinstance(typ, types.Pointer):
            to = typ.to
            if isinstance(to, types.FunctionType):
                return self.function(to)
            if isinstance(to, types.TypedefRef) and isinstance(
                self.resolve(to), types.FunctionType
            ):
                return self(to.name)
            const = "const " if getattr(to, "const", False) else ""
            if isinstance(to, types.Builtin) and to.name == "void":
                return f"?*{const}anyopaque"
            if self.is_opaque(to):
                return f"?*{const}{self.ztype(to)}"
            return f"[*c]{const}{self.ztype(to)}"

        if isinstance(typ, types.Array):
            if param:
                const = "const " if getattr(typ.of, "const", False) else ""
                return f"[*c]{const}{self.ztype(typ.of)}"
            return f"[{typ.length or 0}]{self.ztype(typ.of)}"

        if isinstance(typ, (types.Record, types.TypedefRef)):
            return self(typ.name)

        if isinstance(typ, types.EnumRef):
            return self(typ.name) if typ.name in self.enums else "c_int"

        if isinstance(typ, types.FunctionType):
            return self.function(typ)

        raise ValueError(f"no Zig type for {typ!r}")

    def function(self, typ: types.FunctionType) -> str:
        params = [self.ztype(p.typ, True) for p in typ.params]
        if typ.variadic:
            params.append("...")
        return f"?*const fn ({', '.join(params)}) callconv(.c) {self.ztype(typ.ret)}"

    def is_optional(self, typ) -> bool:
        """Return whether 'typ' is an optional in Zig, not a ``[*c]``"""

        return self.ztype(typ).startswith("?")


def define_value(value) -> str:
    if isinstance(value, decls.StrLiteral):
        return string_literal(value.value, "\\x{:02x}")
    if value.base == 16 and value.value >= 0:
        return hex(value.value)
    return str(value.value)


class Locals(object):
    """Renames the locals of the module's own code, as Zig does not allow a
    local to shadow a declaration, and the C API may declare any name, such as
    'ret' or 'w'. A declared name gets '_' appended."""

    BOUND = {
        "idiomatic": re.compile(r"self|ret|context|s|h|p|err|tag|field|a\d+"),
        "helpers": re.compile(
            r"w|chars|chr|addr|buf|len|fmt|value|bytes|shift|width|idx|unused"
        ),
        "methods": re.compile(r"self|w|indent|obj|flags|o|p|value|(idx|item)\d+"),
    }

    def __init__(self, declared: set):
        self.declared = declared

    def __call__(self, name: str) -> str:
        while name in self.declared:
            name += "_"
        return name

    def renamed(self) -> set:
        """Return the new names of the bound names"""

        return {
            self(name)
            for name in self.declared
            if any(bound.fullmatch(name) for bound in self.BOUND.values())
        }

    def rename(self, text: str, part: str) -> str:
        """Return 'text', a 'part' of the module, with the names it binds
        renamed, except in a doc comment, in a string, after '.' or before
        '('"""

        bound = self.BOUND[part]

        def local(match):
            return self(match[1]) if bound.fullmatch(match[1]) else match[1]

        lines = []
        for line in text.split("\n"):
            if not line.lstrip().startswith("///"):
                parts = re.split(r'("(?:[^"\\]|\\.)*")', line)
                for i in range(0, len(parts), 2):
                    parts[i] = re.sub(r"(?<![.\w@])(\w+)\b(?!\s*\()", local, parts[i])
                line = "".join(parts)
            lines.append(line)
        return "\n".join(lines)


def used(lines: List[str]) -> List[str]:
    """Return 'lines', the body of a printer, discarding 'self' when unused,
    which Zig reports as an error"""

    code = [re.sub(r'"(?:[^"\\]|\\.)*"', '""', line) for line in lines]
    if any(re.search(r"\bself\b", line) for line in code):
        return lines
    return ["_ = self;"] + lines


class Printer(object):
    """Produces the Zig statements that print a record"""

    def __init__(self, namer: Namer, printable: dict, blobs=()):
        self.namer = namer
        self.records = printable
        self.enums = namer.enums
        self.blobs = {r.name for r in blobs}  # the records declared as their bytes

    def value(self, typ, expr: str, depth: int = 0) -> List[str]:
        typ = self.namer.resolve(typ)

        if isinstance(typ, types.Builtin):
            if typ.name in ("float", "double"):
                return [f"try yace_pp.g(w, {expr});"]
            if typ.name == "bool":
                return [f'try w.writeAll(if ({expr}) "true" else "false");']
            if typ.name == "void":
                return ['try w.writeAll("null");']
            return [f'try w.print("{{d}}", .{{{expr}}});']

        if isinstance(typ, types.EnumRef):
            if typ.name in self.namer.enums:
                return [f'try w.print("{{d}}", .{{@intFromEnum({expr})}});']
            return [f'try w.print("{{d}}", .{{{expr}}});']

        if isinstance(typ, (types.Pointer, types.FunctionType)):
            if types.is_string(typ):
                return [f"try yace_pp.str(w, {expr});"]
            if self.namer.is_optional(typ):
                return [f"try yace_pp.ptr(w, if ({expr}) |p| @intFromPtr(p) else 0);"]
            return [f"try yace_pp.ptr(w, @intFromPtr({expr}));"]

        if isinstance(typ, types.Array):
            if not typ.length:
                return ['try w.writeAll("null");']
            elem = self.namer.resolve(typ.of)
            if isinstance(elem, types.Builtin) and elem.name == "char":
                return [f"try yace_pp.strn(w, &{expr});"]
            # Not i<depth>: i0, i1 and so on are integer types in Zig
            idx, item = f"idx{depth}", f"item{depth}"
            lines = [
                'try w.writeAll("[");',
                f"for ({expr}, 0..) |{item}, {idx}| {{",
                f'    if ({idx} > 0) try w.writeAll(", ");',
            ]
            inner = self.value(elem, item, depth + 1)
            if not any(item in ln for ln in inner):  # a record printed as null
                inner.insert(0, f"_ = {item};")
            lines += ["    " + ln for ln in inner]
            lines += ["}", 'try w.writeAll("]");']
            return lines

        if isinstance(typ, types.Record) and typ.name in self.records:
            return [f"try {expr}.{self.method(self.records[typ.name], 'json')}(w);"]

        return ['try w.writeAll("null");']

    def method(self, record, name: str) -> str:
        """Return the name of the printer 'name' of 'record', which no field
        has, as Zig does not allow that"""

        fields = {ident(f.name) for f in record.fields}
        while name in fields:
            name += "_"
        return name

    def record_of(self, typ):
        typ = self.namer.resolve(typ)
        if isinstance(typ, types.Record):
            return self.records.get(typ.name)
        return None

    def accessors(self, record) -> List[str]:
        """Return the methods that read and write the parts of the fields of
        bits of 'record'. A part is an integer of its own width, so Zig rejects
        a wider value without a cast."""

        taken = {ident(f.name) for f in record.fields} | {"format", "cName"}
        taken |= {self.method(record, name) for name in ("json", "yaml", "fpr")}

        def unique(name: str) -> str:
            while name in taken:
                name += "_"
            taken.add(name)
            return name

        lines: List[str] = []
        if record.name in self.blobs:
            return lines
        for field in record.fields:
            typ = self.namer.ztype(field.typ)
            place = f"self.{ident(field.name)}"
            for mask in field.masks:
                name = f"{field.name}_{mask.name}"
                getter = unique(lower_camel(name))
                setter = unique(lower_camel(f"set_{name}"))
                part = f"u{mask.width}"
                lines += [""] if lines else []
                lines += [f"/// {line}".rstrip() for line in doc_lines(mask.doc)]
                lines += [
                    f"pub fn {getter}(self: @This()) {part} {{",
                    f"    return @truncate(({place} & {mask.value:#x}) >> {mask.lo});",
                    "}",
                    "",
                    f"/// Sets the part of '{field.name}' that {getter}() reads",
                    f"pub fn {setter}(self: *@This(), value: {part}) void {{",
                    f"    {place} = ({place} & ~@as({typ}, {mask.value:#x}))"
                    f" | (@as({typ}, value) << {mask.lo});",
                    "}",
                ]
        return lines

    def parts(self, field, expr: str, fmt: str, quote: str) -> List[str]:
        """Return the statements printing a field of bits and its parts as a
        mapping on one line; 'quote' is for the keys, 'fmt' for the values"""

        lines = [f'try w.print("{{{{{quote}{VALUE_KEY}{quote}: {fmt}", .{{{expr}}});']
        for mask in field.masks:
            part = f"({expr} & {mask.value:#x}) >> {mask.lo}"
            lines.append(
                f'try w.print(", {quote}{mask.name}{quote}: {fmt}", .{{{part}}});'
            )
        lines.append('try w.writeAll("}");')
        return lines

    def bits(self, field) -> str:
        """Return the expression that reads the bit-field 'field' from the
        bytes of its record, as the integer type C prints"""

        at = bitfield(field, self.namer.resolve(field.typ), self.enums)
        if at is None:
            raise ValueError(f"'{field.name}' is not a bit-field with an offset")
        args = f"self._bits[{at.first}..{at.first + at.nbytes}], {at.shift}, {at.width}"
        if at.kind == "bool":
            return f"yace_pp.bits({args}) != 0"
        if at.kind == "signed":
            return f"yace_pp.sbits({args})"
        if at.kind == "char":
            # C prints a char with the signedness char has on the platform
            return (
                "if (@typeInfo(c_char).int.signedness == .signed)"
                f" yace_pp.sbits({args})"
                f" else @as(i64, @intCast(yace_pp.bits({args})))"
            )
        return f"yace_pp.bits({args})"

    def fields(self, record) -> list:
        """Return the named fields, which leaves out padding bit-fields"""

        return [f for f in record.fields if f.name]

    def expr_of(self, record, field) -> str:
        """Return the expression of 'field', not a bit-field; a copy from the
        bytes of a blob"""

        if record.name not in self.blobs:
            return f"self.{ident(field.name)}"
        ztype = self.namer.ztype(field.typ)
        return (
            f"std.mem.bytesToValue({ztype},"
            f" self._bits[{field.offset // 8}..][0..@sizeOf({ztype})])"
        )

    def field_value(self, record, field, expr: str) -> List[str]:
        """Return the statements printing 'field', read from a blob's bytes"""

        if record.name not in self.blobs or field.bits is None:
            return self.value(field.typ, expr)
        value = self.bits(field)
        if value.endswith("!= 0"):
            return [f'try w.writeAll(if ({value}) "true" else "false");']
        return [f'try w.print("{{d}}", .{{{value}}});']

    def part_of(self, record, field, expr: str) -> str:
        """Return the expression of a field of bits, for its parts"""

        if record.name in self.blobs and field.bits is not None:
            return f"({self.bits(field)})"
        return expr

    def json_body(self, record) -> List[str]:
        lines = ['try w.writeAll("{");']
        for idx, field in enumerate(self.fields(record)):
            sep = ", " if idx else ""
            lines.append(f'try w.writeAll("{sep}\\"{field.name}\\": ");')
            expr = self.expr_of(record, field)
            if field.masks:
                lines += self.parts(
                    field, self.part_of(record, field, expr), "{d}", '\\"'
                )
                continue
            lines += self.field_value(record, field, expr)
        lines.append('try w.writeAll("}");')
        return used(lines)

    def yaml_body(self, record) -> List[str]:
        lines = []
        for field in self.fields(record):
            expr = self.expr_of(record, field)
            lines.append("try w.splatByteAll(' ', indent);")
            if field.bits is None and self.record_of(field.typ) is not None:
                yaml = self.method(self.record_of(field.typ), "yaml")
                lines.append(f'try w.writeAll("{field.name}:\\n");')
                lines.append(f"try {expr}.{yaml}(w, indent + 2);")
                continue
            lines.append(f'try w.writeAll("{field.name}: ");')
            if field.masks:
                lines += self.parts(
                    field, self.part_of(record, field, expr), "0x{x}", ""
                )
            else:
                lines += self.field_value(record, field, expr)
            lines.append('try w.writeAll("\\n");')
        return used(lines)
