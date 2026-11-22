# SPDX-FileCopyrightText: Simon A. F. Lund <os@safl.dk>
#
# SPDX-License-Identifier: GPL-2.0-only

"""
Rust code for the IR: names, the Rust type of each IR type, and the statements
of the pretty-printers. The Rust target's templates lay out the crate; rgen
produces what goes in it that depends on the types.
"""

import ctypes
from typing import Dict, List, Optional, Sequence

from yace.ir import decls, types
from yace.ir.masks import VALUE_KEY
from yace.ir.model import Model
from yace.targets.capi.target import string_literal
from yace.targets.layout import bitfield
from yace.targets.python.pygen import CTYPES, camel

RUST_TYPES = {
    "bool": "bool",
    "char": "c_char",
    "signed char": "c_schar",
    "unsigned char": "c_uchar",
    "short": "c_short",
    "unsigned short": "c_ushort",
    "int": "c_int",
    "unsigned int": "c_uint",
    "long": "c_long",
    "unsigned long": "c_ulong",
    "long long": "c_longlong",
    "unsigned long long": "c_ulonglong",
    "float": "c_float",
    "double": "c_double",
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
    "as async await break const continue crate dyn else enum extern false fn for"
    " if impl in let loop match mod move mut pub ref return self Self static struct"
    " super trait true type unsafe use where while abstract become box do final gen"
    " macro override priv try typeof unsized virtual yield".split()
)
NOT_RAW = {"crate", "self", "Self", "super"}  # keywords r# cannot escape


def ident(name: str) -> str:
    """'name', usable as a Rust identifier"""

    if name in NOT_RAW:
        return f"{name}_"
    return f"r#{name}" if name in KEYWORDS else name


def doc_lines(doc, errors: str = "", lead: Sequence[str] = ()) -> List[str]:
    """'doc' as the lines of a Rust doc comment, without the '///'; 'lead' is a
    paragraph before its sections, and 'errors' says when the function
    documented returns an error"""

    lines = []
    if doc.brief:
        lines.append(doc.brief)
    for para in [p for p in doc.description.split("\n\n") if p]:
        lines += [""] + para.splitlines()
    for line in doc.prose():
        lines += ["", line]
    if lead:
        lines += ([""] if lines else []) + list(lead)
    if doc.params:
        lines += ["", "# Parameters", ""]
        lines += [f"* `{name}`: {text}" for name, text in doc.params.items()]
    if doc.returns:
        lines += ["", "# Returns", "", doc.returns]
    if errors:
        lines += ["", "# Errors", "", errors]
    return lines


class Namer(object):
    """The Rust names of the IR's types: CamelCase of the C name, or the C name
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
        for rust, cnames in wanted.items():
            for cname in cnames:
                self.names[cname] = ident(rust if len(cnames) == 1 else cname)

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

    def rtype(self, typ, param: bool = False) -> str:
        """The Rust type of 'typ'; a parameter's arrays are pointers, as in C"""

        if isinstance(typ, types.Builtin):
            return "c_void" if typ.name == "void" else RUST_TYPES[typ.name]

        if isinstance(typ, types.Pointer):
            to = typ.to
            if isinstance(to, types.FunctionType):
                return self.function(to)
            if isinstance(to, types.TypedefRef) and isinstance(
                self.resolve(to), types.FunctionType
            ):
                return self(to.name)
            mut = "const" if getattr(to, "const", False) else "mut"
            return f"*{mut} {self.rtype(to)}"

        if isinstance(typ, types.Array):
            if param:
                mut = "const" if getattr(typ.of, "const", False) else "mut"
                return f"*{mut} {self.rtype(typ.of)}"
            return f"[{self.rtype(typ.of)}; {typ.length or 0}]"

        if isinstance(typ, (types.Record, types.EnumRef, types.TypedefRef)):
            if isinstance(typ, types.EnumRef) and typ.name not in self.enums:
                return "c_int"
            return self(typ.name)

        if isinstance(typ, types.FunctionType):
            return self.function(typ)

        raise ValueError(f"no Rust type for {typ!r}")

    def function(self, typ: types.FunctionType) -> str:
        """A nullable pointer to a function of type 'typ', as Rust has them"""

        params = [self.rtype(p.typ, True) for p in typ.params]
        if typ.variadic:
            params.append("...")
        ret = self.ret(typ.ret)
        return f'Option<unsafe extern "C" fn({", ".join(params)}){ret}>'

    def ret(self, typ) -> str:
        if isinstance(typ, types.Builtin) and typ.name == "void":
            return ""
        return f" -> {self.rtype(typ)}"

    def underlying(self, enum: decls.Enum) -> str:
        return self.rtype(enum.underlying) if enum.underlying else "c_int"


def define_type(value) -> str:
    """The type of the Rust constant for a #define"""

    if isinstance(value, decls.StrLiteral):
        return "&CStr"
    if -(2**31) <= value.value < 2**31:
        return "i32"
    if -(2**63) <= value.value < 2**63:
        return "i64"
    return "u64"


def define_value(value) -> str:
    if isinstance(value, decls.StrLiteral):
        return "c" + string_literal(value.value, "\\x{:02x}")
    if value.base == 16 and value.value >= 0:
        return hex(value.value)
    return str(value.value)


PRINTER_METHODS = {"yace_json", "yace_yaml"}


def accessors(record, namer: Namer) -> List[str]:
    """The methods reading and writing the parts of the fields of bits of
    'record'; reading a field of a union is unsafe, writing one is not"""

    union = isinstance(record, decls.Union)
    lines: List[str] = []
    for field in record.fields:
        typ = namer.rtype(field.typ)
        place = f"self.{ident(field.name)}"
        read = f"unsafe {{ {place} }}" if union else place
        for mask in field.masks:
            name = f"{field.name}_{mask.name}"
            if name in PRINTER_METHODS:
                name += "_"
            bits = f"{mask.width} bit{'s' * (mask.width > 1)}"
            lines += [""] if lines else []
            lines += [f"    /// {line}".rstrip() for line in doc_lines(mask.doc)]
            lines += [
                f"    pub fn {name}(&self) -> {typ} {{",
                f"        ({read} & {mask.value:#x}) >> {mask.lo}",
                "    }",
                "",
                f"    /// Set the part of '{field.name}' that {name}() reads",
                "    ///",
                "    /// # Panics",
                "    ///",
                f"    /// When 'value' does not fit in {bits}",
                f"    pub fn set_{name}(&mut self, value: {typ}) {{",
                f'        assert!(value <= {mask.largest:#x}, "{name} is {bits}");',
                f"        {place} = ({read} & !{mask.value:#x})"
                f" | (value << {mask.lo});",
                "    }",
            ]
    return lines


def debug(record, namer: Namer, blob: bool) -> List[str]:
    """A hand-written Debug of 'record', or none where derive(Debug) names its
    fields as C does. Of a union, or of a blob, no field is shown: which member
    of a union is meant is not known, and reading the wrong one may be unsound;
    a blob has no field to read."""

    name = namer(record.name)
    union = isinstance(record, decls.Union)
    renamed = [f for f in record.fields if ident(f.name).removeprefix("r#") != f.name]
    if not (union or blob or renamed):
        return []
    lines = [
        f"impl fmt::Debug for {name} {{",
        "    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {",
        f'        f.debug_struct("{name}")',
    ]
    if union or blob:
        lines.append("            .finish_non_exhaustive()")
    else:
        lines += [
            f'            .field("{field.name}", &{place(record, field)})'
            for field in record.fields
        ]
        lines.append("            .finish()")
    return lines + ["    }", "}"]


def place(record, field) -> str:
    """The expression of 'field' of 'self'; of a packed record, a copy, as a
    reference to the field may not be aligned"""

    expr = f"self.{ident(field.name)}"
    return f"{{ {expr} }}" if record.packed else expr


def receiver(expr: str) -> str:
    """'expr' as the receiver of a method called as a statement, which a block
    would end"""

    return f"({expr})" if expr.startswith("{") else expr


class Printer(object):
    """The Rust statements printing a value of a type as JSON"""

    def __init__(self, model: Model, namer: Namer):
        self.namer = namer
        self.records = {name: r for name, r in model.records().items() if r.fields}
        self.enums = model.enums()
        self.blobs: set = set()  # the records kept as their bytes, by name

    def value(self, typ, expr: str, depth: int = 0) -> List[str]:
        """Statements printing the place 'expr' to 'w'"""

        typ = self.namer.resolve(typ)

        if isinstance(typ, types.Builtin):
            if typ.name in ("float", "double"):
                return [f"w.write_all(yace_pp::g({expr} as f64).as_bytes())?;"]
            if typ.name == "void":
                return ['w.write_all(b"null")?;']
            return [f'write!(w, "{{}}", {expr})?;']

        if isinstance(typ, types.EnumRef):
            return [f'write!(w, "{{}}", {expr}.0)?;']

        if isinstance(typ, types.Pointer):
            if types.is_string(typ):
                # yace_pp::str() takes the pointer by value, which copies the
                # field, so the braces copying a field of a packed record are
                # not needed
                bare = expr[2:-2] if expr.startswith("{ ") else expr
                return [f"yace_pp::str(w, {bare})?;"]
            if self.namer.rtype(typ).startswith("Option<"):
                return [f"yace_pp::ptr(w, {expr}.map_or(0, |f| f as usize))?;"]
            return [f"yace_pp::ptr(w, {expr} as usize)?;"]

        if isinstance(typ, types.Array):
            if not typ.length:
                return ['w.write_all(b"null")?;']
            elem = self.namer.resolve(typ.of)
            if isinstance(elem, types.Builtin) and elem.name == "char":
                return [f"yace_pp::strn(w, &{expr})?;"]
            idx, item = f"i{depth}", f"v{depth}"
            lines = [
                'w.write_all(b"[")?;',
                f"for ({idx}, {item}) in {expr}.iter().copied().enumerate() {{",
                f'    if {idx} > 0 {{ w.write_all(b", ")?; }}',
            ]
            lines += ["    " + ln for ln in self.value(elem, item, depth + 1)]
            lines += ["}", 'w.write_all(b"]")?;']
            return lines

        if isinstance(typ, types.Record):
            if typ.name in self.records:
                return [f"{receiver(expr)}.yace_json(w)?;"]
            return ['w.write_all(b"null")?;']

        if isinstance(typ, types.TypedefRef):
            return ['w.write_all(b"null")?;']

        return ['w.write_all(b"null")?;']

    def record_of(self, typ):
        typ = self.namer.resolve(typ)
        if isinstance(typ, types.Record):
            return self.records.get(typ.name)
        return None

    def parts(self, field, expr: str, fmt: str, quote: str) -> List[str]:
        """The value of a field of bits and of each of its parts, as a mapping
        on one line, with the keys quoted by 'quote', the values by 'fmt'"""

        lines = [f'write!(w, "{{{{{quote}{VALUE_KEY}{quote}: {fmt}", {expr})?;']
        for mask in field.masks:
            part = f"({expr} & {mask.value:#x}) >> {mask.lo}"
            lines.append(f'write!(w, ", {quote}{mask.name}{quote}: {fmt}", {part})?;')
        lines.append('w.write_all(b"}")?;')
        return lines

    def bits(self, field) -> str:
        """The expression reading the bit-field 'field' from 'bytes', the
        bytes of its record, as an integer of the type C prints it as"""

        typ = self.namer.resolve(field.typ)
        at = bitfield(field, typ, self.enums)
        if at is None:
            raise ValueError(f"'{field.name}' is not a bit-field with an offset")
        args = f"&bytes[{at.first}..{at.first + at.nbytes}], {at.shift}, {at.width}"
        if at.kind == "bool":
            return f"yace_pp::bits({args}) != 0"
        if at.kind == "signed":
            return f"yace_pp::sbits({args})"
        if at.kind == "char":
            # As signed as C's char is on the platform, as C prints it
            return (
                f"if c_char::MIN != 0 {{ yace_pp::sbits({args}) }}"
                f" else {{ yace_pp::bits({args}) as i64 }}"
            )
        return f"yace_pp::bits({args})"

    def fields(self, record) -> list:
        """The fields printed: those with a name, not padding bit-fields"""

        return [f for f in record.fields if f.name]

    def head(self, record) -> List[str]:
        """Of a record kept as its bytes, the statement binding 'bytes' to them"""

        if record.name not in self.blobs:
            return []
        return [
            "let bytes = std::slice::from_raw_parts(",
            "    self as *const Self as *const u8,",
            "    std::mem::size_of::<Self>(),",
            ");",
        ]

    def expr_of(self, record, field) -> str:
        """The expression of 'field', other than a bit-field; of a blob, a copy
        read from its bytes"""

        if record.name not in self.blobs:
            return place(record, field)
        rtype = self.namer.rtype(field.typ)
        return (
            f"std::ptr::read_unaligned(bytes.as_ptr().add({field.offset // 8})"
            f" as *const {rtype})"
        )

    def field_value(self, record, field) -> List[str]:
        """Statements printing the value of 'field', of a blob from its bytes"""

        if record.name in self.blobs and field.bits is not None:
            return [f'write!(w, "{{}}", {self.bits(field)})?;']
        return self.value(field.typ, self.expr_of(record, field))

    def json_body(self, record) -> List[str]:
        lines = self.head(record) + ['w.write_all(b"{")?;']
        for idx, field in enumerate(self.fields(record)):
            sep = ", " if idx else ""
            lines.append(f'w.write_all(b"{sep}\\"{field.name}\\": ")?;')
            if field.masks:
                lines += self.parts(field, self.part_of(record, field), "{}", '\\"')
                continue
            lines += self.field_value(record, field)
        lines.append('w.write_all(b"}")?;')
        return lines

    def part_of(self, record, field) -> str:
        """The expression of a field of bits, whose parts are printed"""

        if record.name in self.blobs and field.bits is not None:
            return f"({self.bits(field)})"
        return self.expr_of(record, field)

    def yaml_body(self, record) -> List[str]:
        lines = self.head(record)
        for field in self.fields(record):
            expr = self.expr_of(record, field)
            nested = self.record_of(field.typ) if field.bits is None else None
            if nested is not None:
                lines.append(f'writeln!(w, "{{:indent$}}{field.name}:", "")?;')
                lines.append(f"{receiver(expr)}.yace_yaml(w, indent + 2)?;")
                continue
            lines.append(f'write!(w, "{{:indent$}}{field.name}: ", "")?;')
            if field.masks:
                lines += self.parts(field, self.part_of(record, field), "{:#x}", "")
            else:
                lines += self.field_value(record, field)
            lines.append("writeln!(w)?;")
        return lines


# Methods a record has, or inherits from a trait it derives, that a getter of a
# union's member must not shadow
SIZE_OF = "std::mem::size_of::"

RECORD_METHODS = {"clone", "clone_from", "default", "fmt", "fpr", "pr", "to_string"}


class Unions:
    """Which members of a union safe code may read. Reading a union's member is
    unsafe in Rust because the bytes may not be a value of the member's type.
    Where every member of a union is as large as the union and has no padding,
    a value of the union written through any member, by C or by Rust, has every
    byte initialised; a member of a type for which every bit pattern is a value
    then reads soundly. The sizes are the host's, and the crate asserts them
    when compiled, so a target where they differ fails to build."""

    def __init__(self, model: Model, namer: Namer, blobs):
        self.namer = namer
        self.records = {
            r.name: r for r in model.entities if isinstance(r, decls.RECORDS)
        }
        self.enums = {e.name: e for e in model.entities if isinstance(e, decls.Enum)}
        self.blobs = {r.name for r in blobs}

    def size(self, typ) -> Optional[int]:
        """The size in bytes of a value of 'typ', None where not known"""

        typ = self.namer.resolve(typ)
        if isinstance(typ, types.Builtin):
            if typ.name == "void":
                return None
            return ctypes.sizeof(getattr(ctypes, CTYPES[typ.name].split(".")[1]))
        if isinstance(typ, types.Pointer):
            return ctypes.sizeof(ctypes.c_void_p)
        if isinstance(typ, types.Array):
            size = self.size(typ.of)
            return None if typ.length is None or size is None else typ.length * size
        if isinstance(typ, types.Record):
            record = self.records.get(typ.name)
            return record.size if record and record.fields else None
        if isinstance(typ, types.EnumRef):
            enum = self.enums.get(typ.name)
            if enum and enum.underlying:
                return self.size(enum.underlying)
            return ctypes.sizeof(ctypes.c_int)
        return None

    def dense(self, typ) -> bool:
        """Whether every byte of a value of 'typ' belongs to a field"""

        typ = self.namer.resolve(typ)
        if isinstance(typ, (types.Builtin, types.Pointer, types.EnumRef)):
            return self.size(typ) is not None
        if isinstance(typ, types.Array):
            return typ.length is not None and self.dense(typ.of)
        if not isinstance(typ, types.Record):
            return False
        record = self.records.get(typ.name)
        if record is None or not record.fields:
            return False
        if record.name in self.blobs:
            return True
        if isinstance(record, decls.Union):
            return self.covered(record)
        end = 0
        for field in sorted(record.fields, key=lambda f: f.offset or 0):
            size = self.size(field.typ)
            if field.offset != 8 * end or size is None or not self.dense(field.typ):
                return False
            end += size
        return end == record.size

    def any_bits(self, typ) -> bool:
        """Whether every bit pattern of the size of 'typ' is a value of it in
        Rust: not of a bool, nor of a function pointer, which may not be null
        once Some"""

        typ = self.namer.resolve(typ)
        if isinstance(typ, types.Builtin):
            return typ.name not in ("bool", "void")
        if isinstance(typ, types.Pointer):
            return not isinstance(self.namer.resolve(typ.to), types.FunctionType)
        if isinstance(typ, types.Array):
            return typ.length is not None and self.any_bits(typ.of)
        if isinstance(typ, types.EnumRef):
            return True
        if isinstance(typ, types.Record):
            record = self.records.get(typ.name)
            if record is None or not record.fields:
                return False
            if record.name in self.blobs:
                return True
            return all(self.any_bits(field.typ) for field in record.fields)
        return False

    def covered(self, union) -> bool:
        """Whether every member of 'union' spans all of it, without padding"""

        return bool(union.fields) and all(
            self.size(f.typ) == union.size and self.dense(f.typ) for f in union.fields
        )

    def readable(self, record) -> List[decls.Field]:
        """The members of 'record' that safe code may read, if it is a union"""

        if (
            not isinstance(record, decls.Union)
            or record.name in self.blobs
            or not self.covered(record)
        ):
            return []
        return [f for f in record.fields if self.any_bits(f.typ)]

    def getters(self, record) -> List[str]:
        """The methods reading the members of 'readable(record)'"""

        taken = {
            f"{field.name}_{mask.name}"
            for field in record.fields
            for mask in field.masks
        }
        lines: List[str] = []
        for field in self.readable(record):
            name = field.name + ("_" if field.name in RECORD_METHODS else "")
            if name in taken or name in PRINTER_METHODS:
                continue
            lines += [""] if lines else []
            lines += [
                f"    /// '{field.name}', read without unsafe: every member spans the",
                "    /// whole union, and every bit pattern is a value of its type",
                f"    pub fn {ident(name)}(&self) -> {self.namer.rtype(field.typ)} {{",
                f"        unsafe {{ self.{ident(field.name)} }}",
                "    }",
            ]
        return lines

    def asserts(self, record) -> List[str]:
        """The assertions, at compile time, of the sizes 'readable(record)'
        relies on: each member as large as the union, and each record within
        as large as its fields"""

        name = self.namer(record.name)
        sizes = [
            f"{SIZE_OF}<{self.namer.rtype(f.typ)}>() == {SIZE_OF}<{name}>()"
            for f in record.fields
        ]
        seen = set()

        def within(typ):
            typ = self.namer.resolve(typ)
            if isinstance(typ, types.Array):
                within(typ.of)
            if not isinstance(typ, types.Record) or typ.name in seen:
                return
            seen.add(typ.name)
            inner = self.records[typ.name]
            if inner.name in self.blobs:
                return
            rust = self.namer(inner.name)
            parts = [f"{SIZE_OF}<{self.namer.rtype(f.typ)}>()" for f in inner.fields]
            if isinstance(inner, decls.Union):
                sizes.extend(f"{part} == {SIZE_OF}<{rust}>()" for part in parts)
            else:
                sizes.append(f"{' + '.join(parts)} == {SIZE_OF}<{rust}>()")
            for field in inner.fields:
                within(field.typ)

        for field in record.fields:
            within(field.typ)
        return [f"const _: () = assert!({size});" for size in dict.fromkeys(sizes)]
