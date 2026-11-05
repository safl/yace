"""
Rust code for the IR: names, the Rust type of each IR type, and the statements
of the pretty-printers. The Rust target's templates lay out the crate; this
produces what goes in it that depends on the types.
"""

from typing import Dict, List

from yace.ir import decls, types
from yace.ir.masks import VALUE_KEY
from yace.ir.model import Model
from yace.targets.capi.target import string_literal
from yace.targets.python.pygen import camel

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


def doc_lines(doc) -> List[str]:
    """'doc' as the lines of a Rust doc comment, without the '///'"""

    lines = []
    if doc.brief:
        lines.append(doc.brief)
    for para in [p for p in doc.description.split("\n\n") if p]:
        lines += [""] + para.splitlines()
    if doc.params:
        lines += ["", "# Parameters", ""]
        lines += [f"* `{name}`: {text}" for name, text in doc.params.items()]
    if doc.returns:
        lines += ["", "# Returns", "", doc.returns]
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
            f'            .field("{field.name}", &self.{ident(field.name)})'
            for field in record.fields
        ]
        lines.append("            .finish()")
    return lines + ["    }", "}"]


class Printer(object):
    """The Rust statements printing a value of a type as JSON"""

    def __init__(self, model: Model, namer: Namer):
        self.namer = namer
        self.records = {name: r for name, r in model.records().items() if r.fields}

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
                return [f"yace_pp::str(w, {expr})?;"]
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
                return [f"{expr}.yace_json(w)?;"]
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

    def json_body(self, record) -> List[str]:
        lines = ['w.write_all(b"{")?;']
        for idx, field in enumerate(record.fields):
            sep = ", " if idx else ""
            lines.append(f'w.write_all(b"{sep}\\"{field.name}\\": ")?;')
            expr = f"self.{ident(field.name)}"
            if field.masks:
                lines += self.parts(field, expr, "{}", '\\"')
                continue
            lines += self.value(field.typ, expr)
        lines.append('w.write_all(b"}")?;')
        return lines

    def yaml_body(self, record) -> List[str]:
        lines = []
        for field in record.fields:
            name = ident(field.name)
            nested = self.record_of(field.typ) if field.bits is None else None
            if nested is not None:
                lines.append(f'writeln!(w, "{{:indent$}}{field.name}:", "")?;')
                lines.append(f"self.{name}.yace_yaml(w, indent + 2)?;")
                continue
            lines.append(f'write!(w, "{{:indent$}}{field.name}: ", "")?;')
            if field.masks:
                lines += self.parts(field, f"self.{name}", "{:#x}", "")
            else:
                lines += self.value(field.typ, f"self.{name}")
            lines.append("writeln!(w)?;")
        return lines
