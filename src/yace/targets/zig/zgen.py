# SPDX-FileCopyrightText: Simon A. F. Lund <os@safl.dk>
#
# SPDX-License-Identifier: GPL-2.0-only

"""
Zig code for the IR: names, the Zig type of each IR type, and the statements of
the pretty-printers. The raw layer uses the types C has, as Zig's own
translation of C headers does: C pointers, ``[*c]T``, that may be NULL and point
to any number of elements, optional pointers to opaque types and functions.
"""

import re
from typing import Dict, List

from yace.ir import decls, types
from yace.ir.masks import VALUE_KEY
from yace.ir.model import Model
from yace.targets.capi.target import string_literal
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
    """'name', usable as a Zig identifier"""

    return f'@"{name}"' if name in KEYWORDS else name


def lower_camel(name: str) -> str:
    """Zig names functions in camelCase"""

    text = camel(name)
    return ident(text[:1].lower() + text[1:]) if text else name


def doc_lines(doc, errors: str = "") -> List[str]:
    """'doc' as the lines of a doc comment, without the '///'; 'errors' says
    when it returns an error"""

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
    """The Zig names of the IR's types: CamelCase of the C name, or the C name
    itself where two would get the same one"""

    def __init__(self, model: Model):
        self.records = model.records()
        self.typedefs = model.typedefs()
        self.enums = model.enums()
        self.stubs: Dict[str, str] = {}

        # A typedef of the record or enum of its own name is that type
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
        """Whether 'typ' is a type Zig only knows as opaque"""

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
        """The Zig type of 'typ'; a parameter's arrays are pointers, as in C"""

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
        """Whether the Zig type of 'typ' is an optional, rather than ``[*c]``"""

        return self.ztype(typ).startswith("?")


def define_value(value) -> str:
    if isinstance(value, decls.StrLiteral):
        return string_literal(value.value, "\\x{:02x}")
    if value.base == 16 and value.value >= 0:
        return hex(value.value)
    return str(value.value)


class Locals(object):
    """The names the module's own code binds, each renamed with '_' while the
    module declares it, as Zig forbids a local to shadow a declaration; the
    C API may declare any name, as an enumerator such as 'ret' or 'w'"""

    # What each part of the module binds: the idiomatic functions, the helpers
    # of the printers, and the methods of records and enums
    BOUND = {
        "idiomatic": re.compile(r"self|ret|context|s|h|p|err|tag|field|a\d+"),
        "helpers": re.compile(r"w|chars|chr|addr|buf|len|fmt|value"),
        "methods": re.compile(r"self|w|indent|obj|flags|o|p|value|(idx|item)\d+"),
    }

    def __init__(self, declared: set):
        self.declared = declared

    def __call__(self, name: str) -> str:
        while name in self.declared:
            name += "_"
        return name

    def renamed(self) -> set:
        """What the names declared too are renamed to"""

        return {
            self(name)
            for name in self.declared
            if any(bound.fullmatch(name) for bound in self.BOUND.values())
        }

    def rename(self, text: str, part: str) -> str:
        """'text', a 'part' of the module, with the names it binds renamed,
        other than in a doc comment, a string, after '.' or before '(', where
        the name is not a local's"""

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
    """The body of a printer, 'lines', discarding 'self' where they print none
    of its fields, as Zig rejects an unused parameter"""

    code = [re.sub(r'"(?:[^"\\]|\\.)*"', '""', line) for line in lines]
    if any(re.search(r"\bself\b", line) for line in code):
        return lines
    return ["_ = self;"] + lines


class Printer(object):
    """The Zig statements printing a value of a type as JSON"""

    def __init__(self, namer: Namer, printable: dict):
        self.namer = namer
        self.records = printable

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
            # i0 and the like are integer types in Zig
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
        """The name of the printer 'name' of 'record', other than that of a
        field, as Zig lets no declaration share a field's name"""

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
        """The methods reading and writing the parts of the fields of bits of
        'record', each part an integer of its own width, so a value that does
        not fit is not one Zig lets be passed"""

        taken = {ident(f.name) for f in record.fields} | {"format", "cName"}
        taken |= {self.method(record, name) for name in ("json", "yaml", "fpr")}

        def unique(name: str) -> str:
            while name in taken:
                name += "_"
            taken.add(name)
            return name

        lines: List[str] = []
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
                    f"/// Set the part of '{field.name}' that {getter}() reads",
                    f"pub fn {setter}(self: *@This(), value: {part}) void {{",
                    f"    {place} = ({place} & ~@as({typ}, {mask.value:#x}))"
                    f" | (@as({typ}, value) << {mask.lo});",
                    "}",
                ]
        return lines

    def parts(self, field, expr: str, fmt: str, quote: str) -> List[str]:
        """The value of a field of bits and of each of its parts, as a mapping
        on one line, with the keys quoted by 'quote', the values by 'fmt'"""

        lines = [f'try w.print("{{{{{quote}{VALUE_KEY}{quote}: {fmt}", .{{{expr}}});']
        for mask in field.masks:
            part = f"({expr} & {mask.value:#x}) >> {mask.lo}"
            lines.append(
                f'try w.print(", {quote}{mask.name}{quote}: {fmt}", .{{{part}}});'
            )
        lines.append('try w.writeAll("}");')
        return lines

    def json_body(self, record) -> List[str]:
        lines = ['try w.writeAll("{");']
        for idx, field in enumerate(record.fields):
            sep = ", " if idx else ""
            lines.append(f'try w.writeAll("{sep}\\"{field.name}\\": ");')
            expr = f"self.{ident(field.name)}"
            if field.masks:
                lines += self.parts(field, expr, "{d}", '\\"')
                continue
            lines += self.value(field.typ, expr)
        lines.append('try w.writeAll("}");')
        return used(lines)

    def yaml_body(self, record) -> List[str]:
        lines = []
        for field in record.fields:
            name = ident(field.name)
            lines.append("try w.splatByteAll(' ', indent);")
            if self.record_of(field.typ) is not None:
                yaml = self.method(self.record_of(field.typ), "yaml")
                lines.append(f'try w.writeAll("{field.name}:\\n");')
                lines.append(f"try self.{name}.{yaml}(w, indent + 2);")
                continue
            lines.append(f'try w.writeAll("{field.name}: ");')
            if field.masks:
                lines += self.parts(field, f"self.{name}", "0x{x}", "")
            else:
                lines += self.value(field.typ, f"self.{name}")
            lines.append('try w.writeAll("\\n");')
        return used(lines)
