"""
Go code for the IR: names, the Go type of each IR type and the type cgo gives
it, the conversions between the two, and the methods of the records. The raw
layer declares the records as Go structs of the C layout, with exported fields,
as cgo's own types are of no use outside the package; a union is its bytes,
read and written through a method per member. Pointers are Go pointers, which
may point to C memory; ``void *`` and function pointers are ``unsafe.Pointer``.
"""

import re
from typing import Dict, List, Tuple

from yace.ir import decls, types
from yace.ir.masks import VALUE_KEY
from yace.ir.model import Model
from yace.ir.semantics import is_void_ptr
from yace.targets.capi.target import string_literal
from yace.targets.python.pygen import camel

GO_TYPES = {
    "bool": "bool",
    "char": "byte",
    "signed char": "int8",
    "unsigned char": "uint8",
    "short": "int16",
    "unsigned short": "uint16",
    "int": "int32",
    "unsigned int": "uint32",
    # Its width is the platform's, as in C
    "long": "CLong",
    "unsigned long": "CULong",
    "long long": "int64",
    "unsigned long long": "uint64",
    "float": "float32",
    "double": "float64",
    "int8_t": "int8",
    "int16_t": "int16",
    "int32_t": "int32",
    "int64_t": "int64",
    "uint8_t": "uint8",
    "uint16_t": "uint16",
    "uint32_t": "uint32",
    "uint64_t": "uint64",
    "intptr_t": "int",
    "uintptr_t": "uintptr",
    "size_t": "uintptr",
    "ssize_t": "int",
    "ptrdiff_t": "int",
}

# The names cgo gives the C types
C_TYPES = {
    "bool": "C.bool",
    "char": "C.char",
    "signed char": "C.schar",
    "unsigned char": "C.uchar",
    "short": "C.short",
    "unsigned short": "C.ushort",
    "int": "C.int",
    "unsigned int": "C.uint",
    "long": "C.long",
    "unsigned long": "C.ulong",
    "long long": "C.longlong",
    "unsigned long long": "C.ulonglong",
    "float": "C.float",
    "double": "C.double",
}

KEYWORDS = set(
    "break case chan const continue default defer else fallthrough for func go"
    " goto if import interface map package range return select struct switch"
    " type var".split()
)

# Go's predeclared identifiers, which a parameter or local must not shadow, as
# the generated code may use them
PREDECLARED = set(
    "any append bool byte cap clear close comparable complex complex128 complex64"
    " copy delete error false float32 float64 imag int int16 int32 int64 int8"
    " iota len make max min new nil panic print println real recover rune string"
    " true uint uint16 uint32 uint64 uint8 uintptr".split()
)

# The packages the generated code imports, which nothing may shadow
IMPORTS = {"C", "cgo", "errors", "fmt", "io", "math", "strconv", "syscall", "unsafe"}

# What the package declares of its own, before any name of the C API
OWN = {"CLong", "CULong"}

# The alignment of a Go type of that many bytes, for a record kept as bytes
ALIGNED = {1: "uint8", 2: "uint16", 4: "uint32", 8: "uint64"}


def export(name: str) -> str:
    """'name', exported, as Go exports what begins with an upper-case letter"""

    if name[:1].islower():
        return name[:1].upper() + name[1:]
    if not name[:1].isupper():
        return f"X{name}"
    return name


def ident(name: str) -> str:
    """'name', usable as a local Go identifier"""

    return f"{name}_" if name in KEYWORDS or name in PREDECLARED else name


def doc_lines(doc) -> List[str]:
    """The lines of a doc comment, unindented, which Go would read as code, and
    a paragraph of one line ending in a full stop, which Go would read as a
    heading otherwise"""

    def para(lines: List[str]) -> List[str]:
        if len(lines) == 1 and not lines[0].endswith((".", "!", "?", ":", ";")):
            return [f"{lines[0]}."]
        return lines

    lines = []
    if doc.brief:
        lines.append(doc.brief)
    for text in [p for p in doc.description.split("\n\n") if p]:
        lines += [""] + para([line.strip() for line in text.splitlines()])
    if doc.returns:
        lines += [""] + para([f"Returns {doc.returns}"])
    return lines


def comment(lines: List[str], indent: str = "") -> List[str]:
    return [f"{indent}// {line}".rstrip() for line in lines]


def define_value(value) -> str:
    if isinstance(value, decls.StrLiteral):
        return string_literal(value.value, "\\x{:02x}")
    if value.base == 16 and value.value >= 0:
        return hex(value.value)
    return str(value.value)


def align(rows: List[Tuple[List[str], List[str]]], indent: str = "\t") -> List[str]:
    """The lines of 'rows', each its comment lines and its cells, with the cells
    padded as gofmt pads them: across the rows that follow each other with no
    comment line between them"""

    lines: List[str] = []
    section: List[List[str]] = []

    def flush():
        widths: Dict[int, int] = {}
        for cells in section:
            for idx, cell in enumerate(cells[:-1]):
                widths[idx] = max(widths.get(idx, 0), len(cell))
        for cells in section:
            padded = [c.ljust(widths[i]) for i, c in enumerate(cells[:-1])]
            lines.append(indent + " ".join(padded + cells[-1:]))
        section.clear()

    for docs, cells in rows:
        if docs:
            flush()
            lines += comment(docs, indent)
        section.append(cells)
    flush()
    return lines


class Registry(object):
    """Names, each other than those before it, by a trailing '_'"""

    def __init__(self, taken=()):
        self.taken = set(taken)

    def add(self, name: str) -> str:
        while name in self.taken:
            name += "_"
        self.taken.add(name)
        return name


class Namer(object):
    """The Go names of the package: of the types, CamelCase of the C name, or the
    C name itself, exported, where two would get the same one; of the constants
    and raw functions, the C name exported. Each is other than those named
    before it, by a trailing '_'."""

    def __init__(self, model: Model):
        self.records = model.records()
        self.typedefs = model.typedefs()
        self.enums = model.enums()
        self.registry = Registry(OWN)
        self.stubs: Dict[str, str] = {}

        # A typedef of the record or enum of its own name is that type
        self.aliases = {
            name
            for name, typedef in self.typedefs.items()
            if isinstance(typedef.typ, (types.Record, types.EnumRef))
            and typedef.typ.name == name
        }
        named = [("tag", n) for n in [*self.records, *self.enums]]
        named += [("typedef", n) for n in self.typedefs if n not in self.aliases]
        wanted: Dict[str, int] = {}
        for _, cname in named:
            wanted[camel(cname)] = wanted.get(camel(cname), 0) + 1
        self.names: Dict[Tuple[str, str], str] = {}
        for key in named:
            go = camel(key[1])
            self.names[key] = self.registry.add(
                go if go and wanted[go] == 1 else export(key[1])
            )

    def type_name(self, typ) -> str:
        """The name of the record, enum or typedef 'typ' names"""

        if isinstance(typ, types.TypedefRef) and typ.name not in self.aliases:
            key = ("typedef", typ.name)
        else:
            key = ("tag", typ.name)
        if key in self.names:
            return self.names[key]
        if typ.name not in self.stubs:
            self.stubs[typ.name] = self.registry.add(
                camel(typ.name) or export(typ.name)
            )
        return self.stubs[typ.name]

    def resolve(self, typ):
        while isinstance(typ, types.TypedefRef) and typ.name in self.typedefs:
            typ = self.typedefs[typ.name].typ
        return typ

    def is_function_ptr(self, typ) -> bool:
        typ = self.resolve(typ)
        if not isinstance(typ, types.Pointer):
            return False
        return isinstance(self.resolve(typ.to), types.FunctionType)

    def is_opaque(self, typ) -> bool:
        """Whether 'typ' is one Go knows nothing of but its name"""

        typ = self.resolve(typ)
        if isinstance(typ, types.Record):
            record = self.records.get(typ.name)
            return record is None or (not record.fields and record.size is None)
        return isinstance(typ, types.TypedefRef)

    def gotype(self, typ, param: bool = False) -> str:
        """The Go type of 'typ'; a parameter's arrays are pointers, as in C"""

        if param and isinstance(self.resolve(typ), types.Array):
            typ = self.resolve(typ)
        if isinstance(typ, types.Builtin):
            return "" if typ.name == "void" else GO_TYPES[typ.name]
        if isinstance(typ, types.Pointer):
            to = self.resolve(typ.to)
            if isinstance(to, types.FunctionType) or is_void_ptr(typ):
                return "unsafe.Pointer"
            return f"*{self.gotype(typ.to)}"
        if isinstance(typ, types.Array):
            if param:
                return f"*{self.gotype(typ.of)}"
            return f"[{typ.length or 0}]{self.gotype(typ.of)}"
        if isinstance(typ, (types.Record, types.TypedefRef)):
            return self.type_name(typ)
        if isinstance(typ, types.EnumRef):
            if typ.name in self.enums:
                return self.type_name(typ)
            return "int32"
        if isinstance(typ, types.FunctionType):
            return "unsafe.Pointer"
        raise ValueError(f"no Go type for {typ!r}")

    def ctype(self, typ, param: bool = False) -> str:
        """The type cgo gives 'typ'"""

        if param and isinstance(self.resolve(typ), types.Array):
            typ = self.resolve(typ)
        if isinstance(typ, types.Builtin):
            return C_TYPES.get(typ.name, f"C.{typ.name}")
        if isinstance(typ, types.Pointer):
            to = self.resolve(typ.to)
            if is_void_ptr(typ):
                return "unsafe.Pointer"
            if isinstance(to, types.FunctionType):
                return "*[0]byte"
            return f"*{self.ctype(typ.to)}"
        if isinstance(typ, types.Array):
            if param:
                return f"*{self.ctype(typ.of)}"
            return f"[{typ.length or 0}]{self.ctype(typ.of)}"
        if isinstance(typ, types.Record):
            return f"C.{typ.tag}_{typ.name}"
        if isinstance(typ, types.TypedefRef):
            return f"C.{typ.name}"
        if isinstance(typ, types.EnumRef):
            return f"C.enum_{typ.name}"
        if isinstance(typ, types.FunctionType):
            return "*[0]byte"
        raise ValueError(f"no cgo type for {typ!r}")

    def kind(self, typ) -> str:
        """How a value of 'typ' crosses to C: as a 'scalar', a 'pointer', a
        'record' by value, or 'none', void"""

        resolved = self.resolve(typ)
        if isinstance(resolved, types.Builtin):
            return "none" if resolved.name == "void" else "scalar"
        if isinstance(resolved, types.EnumRef):
            return "scalar"
        if isinstance(resolved, (types.Pointer, types.Array, types.FunctionType)):
            return "pointer"
        return "record"

    def by_value(self, typ) -> bool:
        """Whether Go can hold a 'typ' by value: not one it only knows the name
        of, such as a va_list, declared outside the headers"""

        resolved = self.resolve(typ)
        if isinstance(resolved, types.Array) and resolved.length is not None:
            return self.by_value(resolved.of)
        return self.kind(typ) != "record" or not self.is_opaque(resolved)

    def to_c(self, typ, expr: str, param: bool = True) -> str:
        """'expr', of the Go type of 'typ', as cgo takes it"""

        kind = self.kind(typ)
        ctype = self.ctype(typ, param)
        if kind == "scalar":
            return f"{ctype}({expr})"
        if kind == "pointer":
            if ctype == "unsafe.Pointer":
                return expr if self.gotype(typ, param) == ctype else f"{ctype}({expr})"
            return f"({ctype})(unsafe.Pointer({expr}))"
        return f"*(*{ctype})(unsafe.Pointer(&{expr}))"

    def from_c(self, typ, expr: str) -> str:
        """'expr', as cgo gives a 'typ', as its Go type; a record, addressable"""

        kind = self.kind(typ)
        gotype = self.gotype(typ)
        if kind == "scalar":
            return f"{gotype}({expr})"
        if kind == "pointer":
            if self.ctype(typ) == "unsafe.Pointer":
                return expr if gotype == "unsafe.Pointer" else f"{gotype}({expr})"
            return f"({gotype})(unsafe.Pointer({expr}))"
        return f"*(*{gotype})(unsafe.Pointer(&{expr}))"


class Records(object):
    """The Go declarations of the records, and their methods: the members of a
    union, the printers and the parts of the fields of bits"""

    def __init__(self, namer: Namer, complete: List):
        self.namer = namer
        # Go knows nothing of the bit-fields of a record kept as its bytes
        self.printable = {r.name for r in complete if not self.is_blob(r)}
        self.fields: Dict[str, Dict[str, str]] = {}
        self.methods: Dict[str, Dict[str, str]] = {}
        self.printer = Printer(namer, self)

    def is_blob(self, record) -> bool:
        return bool(record.size) and any(f.bits is not None for f in record.fields)

    def is_bytes(self, record) -> bool:
        """Whether 'record' is declared as its bytes: a blob, or packed, as Go
        aligns every field"""

        return self.is_blob(record) or (record.packed and bool(record.fields))

    def is_flexible(self, record, field) -> bool:
        """Whether 'field' is a flexible array, which Go cannot declare: a
        zero-sized last field would pad the struct"""

        typ = self.namer.resolve(field.typ)
        return (
            field is record.fields[-1]
            and isinstance(typ, types.Array)
            and not typ.length
        )

    def field_names(self, record) -> Dict[str, str]:
        """The Go names of the fields of a struct, or of the methods of the
        members of a union, by C name"""

        if record.name not in self.fields:
            registry = Registry()
            self.fields[record.name] = {
                f.name: registry.add(export(f.name)) for f in record.fields if f.name
            }
        return self.fields[record.name]

    def method_names(self, record) -> Dict[str, str]:
        """The names of the methods of 'record', other than its fields'"""

        if record.name not in self.methods:
            names = self.field_names(record)
            registry = Registry(names.values())
            found = {}
            if record.packed and not self.is_blob(record):
                for field in record.fields:
                    if field.name and not self.is_flexible(record, field):
                        found[f"set:{field.name}"] = registry.add(
                            f"Set{names[field.name]}"
                        )
            if record.name in self.printable:
                found["Fpr"] = registry.add("Fpr")
                found["String"] = registry.add("String")
            if not self.is_blob(record):
                for field in record.fields:
                    for mask in field.masks:
                        name = f"{field.name}_{mask.name}"
                        found[name] = registry.add(camel(name))
                        found[f"set_{name}"] = registry.add(camel(f"set_{name}"))
            self.methods[record.name] = found
        return self.methods[record.name]

    def bytes(self, record) -> List[str]:
        """The fields of a record kept as its bytes, aligned as the record"""

        aligned = ALIGNED.get(record.align or 1, "uint64")
        return align(
            [([], ["_", f"[0]{aligned}"]), ([], ["bytes", f"[{record.size or 0}]byte"])]
        )

    def declare(self, record, name: str) -> List[str]:
        lines = comment(doc_lines(record.doc))
        if not record.fields and record.size is None:
            return lines + [f"type {name} struct{{ _ [0]byte }}"]
        if self.is_bytes(record) or isinstance(record, decls.Union):
            if lines:
                lines.append("//")
            if self.is_blob(record):
                lines += [
                    "// Its bit-fields have no counterpart in Go: only its size and",
                    "// alignment are kept.",
                ]
            elif record.packed:
                lines += [
                    "// Packed, which Go cannot declare, as it aligns every field:",
                    "// each field is read and written by a copy, through its methods.",
                    "// The garbage collector does not see a pointer set in a field,",
                    "// so what it points to must be kept alive by other means.",
                ]
            else:
                lines += [
                    "// A union, its members read and written through the method of",
                    "// each, as Go has no unions.",
                ]
            return lines + [f"type {name} struct {{"] + self.bytes(record) + ["}"]

        names = self.field_names(record)
        rows: List[Tuple[List[str], List[str]]] = []
        notes = []
        for field in record.fields:
            if self.is_flexible(record, field):
                notes.append(
                    f"// '{field.name}', a flexible array, follows it in memory: Go"
                )
                notes.append("// cannot declare it, as a struct may not end in one.")
                # Its alignment is the struct's, which pads it as in C
                aligned = ALIGNED.get(record.align or 1, "uint64")
                rows.insert(0, ([], ["_", f"[0]{aligned}"]))
                continue
            docs = [" ".join(field.doc.brief.split())] if field.doc.brief else []
            rows.append((docs, [names[field.name], self.namer.gotype(field.typ)]))
        if notes:
            lines += (["//"] if lines else []) + notes
        return lines + [f"type {name} struct {{"] + align(rows) + ["}"]

    def packed_fields(self, record, name: str) -> List[str]:
        """The methods reading and writing each field of a packed record, in its
        bytes at its offset, which may not be aligned for it; a getter has a
        value receiver, so that it reads what another getter returns"""

        names = self.field_names(record)
        setters = self.method_names(record)
        lines: List[str] = []
        for field in record.fields:
            if not field.name or self.is_flexible(record, field):
                continue
            getter, setter = names[field.name], setters[f"set:{field.name}"]
            if field.offset is None:
                raise ValueError(
                    f"'{record.name}' is packed, and '{field.name}' has no offset"
                )
            typ = self.namer.gotype(field.typ)
            at = f"r.bytes[{field.offset // 8}:]"
            brief = " ".join(field.doc.brief.split())
            lines += [""] + comment(
                [
                    f"{getter} is the field '{field.name}'"
                    + (f": {brief}" if brief else "")
                ]
            )
            lines += [
                f"func (r {name}) {getter}() {typ} {{",
                f"\treturn yaceGet[{typ}]({at})",
                "}",
                "",
                f"// {setter} sets the field '{field.name}'",
                f"func (r *{name}) {setter}(value {typ}) {{",
                f"\tyaceSet({at}, value)",
                "}",
            ]
        return lines

    def members(self, record, name: str) -> List[str]:
        """The method of each member of a union, the member in its bytes"""

        lines: List[str] = []
        for field in record.fields:
            method = self.field_names(record)[field.name]
            typ = self.namer.gotype(field.typ)
            brief = " ".join(field.doc.brief.split())
            lines += [""] + comment(
                [
                    f"{method} is the member '{field.name}'"
                    + (f": {brief}" if brief else "")
                ]
            )
            lines += [
                f"func (u *{name}) {method}() *{typ} {{",
                f"\treturn (*{typ})(unsafe.Pointer(&u.bytes))",
                "}",
            ]
        return lines

    def accessors(self, record, name: str) -> List[str]:
        """The methods reading and writing the parts of the fields of bits of
        'record'; a value that does not fit its part panics. Of a packed record,
        a getter has a value receiver, as those of its fields do"""

        if self.is_blob(record):
            return []
        methods = self.method_names(record)
        union = isinstance(record, decls.Union)
        lines: List[str] = []
        receiver = f"r {name}" if record.packed else f"r *{name}"
        for field in record.fields:
            typ = self.namer.gotype(field.typ)
            member = self.field_names(record)[field.name]
            place = f"(*r.{member}())" if union else f"r.{member}"
            read = f"r.{member}()" if record.packed else place
            for mask in field.masks:
                part = f"{field.name}_{mask.name}"
                getter, setter = methods[part], methods[f"set_{part}"]
                lines += [""] + comment(doc_lines(mask.doc))
                lines += [
                    f"func ({receiver}) {getter}() {typ} {{",
                    f"\treturn ({read} & {mask.value:#x}) >> {mask.lo}",
                    "}",
                    "",
                    f"// {setter} sets the part of '{field.name}' that {getter} reads;",
                    "// it panics on a value that does not fit the part's"
                    f" {mask.width} bit{'s' * (mask.width > 1)}.",
                    f"func (r *{name}) {setter}(value {typ}) {{",
                    f"\tif value > {mask.largest:#x} {{",
                    f'\t\tpanic("{name}.{setter}: " + strconv.FormatUint(uint64(value),'
                    ' 10) + " does not fit")',
                    "\t}",
                    (
                        f"\tr.{methods['set:' + field.name]}("
                        f"{read}&^{mask.value:#x} | value<<{mask.lo})"
                        if record.packed
                        else f"\t{place} = {place}&^{mask.value:#x} | value<<{mask.lo}"
                    ),
                    "}",
                ]
        return lines

    def printers(self, record, name: str, prefix: str) -> List[str]:
        """Fpr() and String(), printing what the C API's pretty-printers
        print, without calling them"""

        if record.name not in self.printable:
            return []
        methods = self.method_names(record)
        fpr, string = methods["Fpr"], methods["String"]
        printer = self.printer
        lines = [
            "",
            f"func (r *{name}) yaceJSON(out []byte) []byte {{",
            *["\t" + line for line in printer.json_body(record)],
            "}",
            "",
            f"func (r *{name}) yaceYAML(out []byte, indent int) []byte {{",
            *["\t" + line for line in printer.yaml_body(record)],
            "}",
            "",
            f"// {fpr} prints r, or null when nil, to w, as {record.name}_fpr() does:",
            f"// as YAML, or as JSON on one line, by flags, one of {prefix}_PR_*",
            f"func (r *{name}) {fpr}(w io.Writer, flags int) error {{",
            "\tvar out []byte",
            "\tswitch {",
            f"\tcase flags&{prefix}_PR_JSON != 0 && r == nil:",
            '\t\tout = append(out, "null\\n"...)',
            f"\tcase flags&{prefix}_PR_JSON != 0:",
            "\t\tout = append(r.yaceJSON(out), '\\n')",
            "\tcase r == nil:",
            f'\t\tout = append(out, "{record.name}: ~\\n"...)',
            "\tdefault:",
            f'\t\tout = r.yaceYAML(append(out, "{record.name}:\\n"...), 2)',
            "\t}",
            "\t_, err := w.Write(out)",
            "\treturn err",
            "}",
        ]
        if string == "String":
            lines += [
                "",
                "// String is the YAML of r, as Fpr prints it",
                f"func (r {name}) String() string {{",
                f'\treturn string(r.yaceYAML([]byte("{record.name}:\\n"), 2))',
                "}",
            ]
        return lines


class Printer(object):
    """The Go statements appending to the []byte 'out' a value of a type, as
    the pretty-printers of the C API print it"""

    def __init__(self, namer: Namer, records: "Records"):
        self.namer = namer
        self.records = records

    def printable(self, typ):
        """The record 'typ' is, if it is one with printers"""

        typ = self.namer.resolve(typ)
        if isinstance(typ, types.Record):
            record = self.namer.records.get(typ.name)
            if record is not None and record.name in self.records.printable:
                return record
        return None

    def value(self, typ, expr: str, depth: int = 0) -> List[str]:
        typ = self.namer.resolve(typ)
        null = ['out = append(out, "null"...)']

        if isinstance(typ, types.Builtin):
            name = typ.name
            if name == "bool":
                return [f"out = yaceBool(out, {expr})"]
            if name in ("float", "double"):
                return [f"out = yaceG(out, float64({expr}))"]
            if name.startswith(("unsigned", "uint")) or name == "size_t":
                return [f"out = strconv.AppendUint(out, uint64({expr}), 10)"]
            if name == "void":
                return null
            if name == "char":
                # As signed as C's char is on the platform, as C prints it
                return [f"out = strconv.AppendInt(out, int64(C.char({expr})), 10)"]
            return [f"out = strconv.AppendInt(out, int64({expr}), 10)"]

        if isinstance(typ, types.EnumRef):
            return [f"out = strconv.AppendInt(out, int64({expr}), 10)"]

        if isinstance(typ, types.Pointer):
            if types.is_string(typ):
                return [f"out = yaceStr(out, unsafe.Pointer({expr}))"]
            return [f"out = yacePtr(out, uintptr(unsafe.Pointer({expr})))"]

        if isinstance(typ, types.Array):
            if typ.length is None:
                return null
            elem = self.namer.resolve(typ.of)
            if isinstance(elem, types.Builtin) and elem.name == "char":
                return [f"out = yaceStrn(out, {expr}[:])"]
            idx = f"i{depth}"
            # A member of a union is ranged over by its pointer, as gofmt drops
            # the parentheses of '(*r.Member())' there
            ranged = (
                expr[2:-1] if expr.startswith("(*") and expr.endswith(")") else expr
            )
            lines = [
                "out = append(out, '[')",
                f"for {idx} := range {ranged} {{",
                f"\tif {idx} > 0 {{",
                '\t\tout = append(out, ", "...)',
                "\t}",
            ]
            inner = self.value(elem, f"{expr}[{idx}]", depth + 1)
            if not any(f"[{idx}]" in line for line in inner):
                lines[1] = f"for {idx} := 0; {idx} < len({ranged}); {idx}++ {{"
            lines += ["\t" + line for line in inner]
            return lines + ["}", "out = append(out, ']')"]

        if isinstance(typ, types.Record) and self.printable(typ) is not None:
            return [f"out = {expr}.yaceJSON(out)"]

        return null

    def place(self, record, field) -> str:
        """The expression of 'field' of the record 'r'; of a packed record, the
        local 'v', see bound()"""

        name = self.records.field_names(record)[field.name]
        if record.packed:
            return "v"
        return f"(*r.{name}())" if isinstance(record, decls.Union) else f"r.{name}"

    def bound(self, record, field, lines: List[str]) -> List[str]:
        """'lines', in a block binding the local 'v' to a copy of 'field' of a
        packed record, if they use it, for them to take its address"""

        if not record.packed or not any(re.search(r"\bv\b", ln) for ln in lines):
            return lines
        name = self.records.field_names(record)[field.name]
        return ["{", f"\tv := r.{name}()", *["\t" + ln for ln in lines], "}"]

    def parts(self, field, expr: str, base: int, quote: str) -> List[str]:
        """The value of a field of bits and of each of its parts, as a mapping
        on one line, with the keys quoted by 'quote', the values in 'base'"""

        prefix = "0x" if base == 16 else ""
        value = f"uint64({expr})"

        def put(text: str, part: str) -> List[str]:
            return [
                f"out = append(out, {go_quote(text + prefix)}...)",
                f"out = strconv.AppendUint(out, {part}, {base})",
            ]

        lines = put(f"{{{quote}{VALUE_KEY}{quote}: ", value)
        for mask in field.masks:
            lines += put(
                f", {quote}{mask.name}{quote}: ",
                f"{value}&{mask.value:#x}>>{mask.lo}",
            )
        return lines + ["out = append(out, '}')"]

    def named(self, record) -> list:
        """The fields printed: those with a name, not padding bit-fields"""

        return [f for f in record.fields if f.name]

    def json_body(self, record) -> List[str]:
        lines = ["out = append(out, '{')"]
        for idx, field in enumerate(self.named(record)):
            sep = ", " if idx else ""
            key = go_quote(f'{sep}"{field.name}": ')
            lines.append(f"out = append(out, {key}...)")
            if self.records.is_flexible(record, field):
                lines.append('out = append(out, "null"...)')
            elif field.masks:
                printed = self.parts(field, self.place(record, field), 10, '"')
                lines += self.bound(record, field, printed)
            else:
                printed = self.value(field.typ, self.place(record, field))
                lines += self.bound(record, field, printed)
        return lines + ["return append(out, '}')"]

    def yaml_body(self, record) -> List[str]:
        lines = []
        for field in self.named(record):
            lines.append("out = yaceIndent(out, indent)")
            if self.records.is_flexible(record, field):
                lines.append(f"out = append(out, {go_quote(field.name + ': null')}...)")
                lines.append("out = append(out, '\\n')")
                continue
            place = self.place(record, field)
            if self.printable(field.typ) is not None:
                lines.append(f"out = append(out, {go_quote(field.name + ':')}...)")
                lines.append("out = append(out, '\\n')")
                printed = [f"out = {place}.yaceYAML(out, indent+2)"]
                lines += self.bound(record, field, printed)
                continue
            lines.append(f"out = append(out, {go_quote(field.name + ': ')}...)")
            if field.masks:
                printed = self.parts(field, place, 16, "")
            else:
                printed = self.value(field.typ, place)
            lines += self.bound(record, field, printed)
            lines.append("out = append(out, '\\n')")
        return lines + ["return out"]


def go_quote(text: str) -> str:
    """'text' as a Go string literal"""

    return string_literal(text, "\\x{:02x}")
