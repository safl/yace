"""
Python code for the IR: names, and the ctypes type of each IR type. The Python
target's templates lay out the module; this produces what goes in it that
depends on the types.
"""

import ctypes
import keyword
from typing import Dict, List

from yace.ir import decls, types
from yace.ir.model import Model

CTYPES = {
    "bool": "ctypes.c_bool",
    "char": "ctypes.c_char",
    "signed char": "ctypes.c_byte",
    "unsigned char": "ctypes.c_ubyte",
    "short": "ctypes.c_short",
    "unsigned short": "ctypes.c_ushort",
    "int": "ctypes.c_int",
    "unsigned int": "ctypes.c_uint",
    "long": "ctypes.c_long",
    "unsigned long": "ctypes.c_ulong",
    "long long": "ctypes.c_longlong",
    "unsigned long long": "ctypes.c_ulonglong",
    "float": "ctypes.c_float",
    "double": "ctypes.c_double",
    "int8_t": "ctypes.c_int8",
    "int16_t": "ctypes.c_int16",
    "int32_t": "ctypes.c_int32",
    "int64_t": "ctypes.c_int64",
    "uint8_t": "ctypes.c_uint8",
    "uint16_t": "ctypes.c_uint16",
    "uint32_t": "ctypes.c_uint32",
    "uint64_t": "ctypes.c_uint64",
    # ctypes has no intptr_t or ptrdiff_t; Py_ssize_t has their width
    "intptr_t": "ctypes.c_ssize_t",
    "uintptr_t": "ctypes.c_size_t",
    "size_t": "ctypes.c_size_t",
    "ssize_t": "ctypes.c_ssize_t",
    "ptrdiff_t": "ctypes.c_ssize_t",
}


def ident(name: str) -> str:
    """'name', usable as a Python identifier"""

    return f"{name}_" if keyword.iskeyword(name) else name


def camel(name: str) -> str:
    return "".join(part[:1].upper() + part[1:] for part in name.split("_") if part)


def docstring(doc, indent: str = "", params: bool = True) -> str:
    """'doc' as the body of a docstring, or empty when there is none"""

    def safe(text: str) -> str:
        return text.replace("\\", "\\\\").replace('"""', '\\"\\"\\"')

    parts = []
    if doc.brief:
        parts.append(safe(doc.brief))
    parts += [safe(p) for p in doc.description.split("\n\n") if p]
    if params and doc.params:
        lines = ["Args:"]
        lines += [f"    {name}: {safe(text)}" for name, text in doc.params.items()]
        parts.append(f"\n{indent}".join(lines))
    if doc.returns:
        parts.append(f"Returns:\n{indent}    {safe(doc.returns)}")
    return f"\n\n{indent}".join(parts)


def quoted(body: str, indent: str = "") -> str:
    """'body' as a docstring; one ending in a quote would end it early"""

    if "\n" in body:
        return f'"""{body}\n{indent}"""'
    if body.endswith('"'):
        body = body[:-1] + '\\"'
    return f'"""{body}"""'


# The unsigned integers of each alignment, of which a blob is made
BLOB_UNITS = {
    1: "ctypes.c_uint8",
    2: "ctypes.c_uint16",
    4: "ctypes.c_uint32",
    8: "ctypes.c_uint64",
}


class Namer(object):
    """The Python names of the IR's types: CamelCase of the C name, or the C
    name itself where two would get the same one"""

    def __init__(self, model: Model):
        self.model = model
        self.records = model.records()
        self.typedefs = model.typedefs()
        self.enums = model.enums()
        self.stubs: Dict[str, str] = {}  # names the IR does not define

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
        for py, cnames in wanted.items():
            for cname in cnames:
                self.names[cname] = ident(py if len(cnames) == 1 else cname)

    def __call__(self, cname: str) -> str:
        if cname in self.names:
            return self.names[cname]
        if cname not in self.stubs:
            self.stubs[cname] = ident(camel(cname) or cname)
        return self.stubs[cname]

    def is_blob(self, record) -> bool:
        """Whether ctypes cannot lay out the record as C does: an unnamed
        bit-field sets no alignment in C, but does in ctypes, which refuses one
        of width 0; ctypes starts bit-fields of another type, and a field after
        one, in a unit of their own, where GCC packs them in what is left"""

        bits = [f for f in record.fields if f.bits is not None]
        if not record.size or not bits:
            return False
        if any(not f.name for f in bits) or any(f.typ != bits[0].typ for f in bits):
            return True
        if any(self.resolve(f.typ) == types.Builtin(name="char") for f in bits):
            return True  # ctypes.c_char has no bit-fields
        fields = record.fields
        for before, after in zip([None] + fields, fields):
            if after.bits is not None and (before is None or before.bits is None):
                # A run of bit-fields GCC starts in what the field before left
                unit = self.bits_of(after.typ)
                if unit is None or after.offset is None or after.offset % unit:
                    return True
            if before is None or before.bits is None or after.bits is not None:
                continue
            unit = self.bits_of(before.typ)
            if unit is None or before.offset is None or after.offset is None:
                return True
            if after.offset < before.offset // unit * unit + unit:
                return True
        return False

    def bits_of(self, typ):
        """The bits of the integer 'typ', a bit-field's unit; None if unknown"""

        typ = self.resolve(typ)
        if isinstance(typ, types.EnumRef):
            enum = self.enums.get(typ.name)
            typ = enum.underlying if enum is not None and enum.underlying else None
        if not isinstance(typ, types.Builtin) or typ.name not in CTYPES:
            return None
        return 8 * ctypes.sizeof(getattr(ctypes, CTYPES[typ.name].split(".")[1]))

    def resolve(self, typ):
        while isinstance(typ, types.TypedefRef) and typ.name in self.typedefs:
            typ = self.typedefs[typ.name].typ
        return typ

    def ctype(self, typ, param: bool = False) -> str:
        """The ctypes type of 'typ'; a parameter's arrays are pointers, as in C"""

        if isinstance(typ, types.Builtin):
            return "None" if typ.name == "void" else CTYPES[typ.name]

        if isinstance(typ, types.Pointer):
            if types.is_string(typ):
                return "ctypes.c_char_p"
            to = typ.to
            if isinstance(to, types.Builtin) and to.name == "void":
                return "ctypes.c_void_p"
            if isinstance(to, types.FunctionType):
                return self.function(to)
            if isinstance(to, types.TypedefRef) and isinstance(
                self.resolve(to), types.FunctionType
            ):
                return self(to.name)
            return f"ctypes.POINTER({self.ctype(to)})"

        if isinstance(typ, types.Array):
            if param:
                return f"ctypes.POINTER({self.ctype(typ.of)})"
            return f"({self.ctype(typ.of)} * {typ.length or 0})"

        if isinstance(typ, types.Record):
            return self(typ.name)

        if isinstance(typ, types.EnumRef):
            enum = self.enums.get(typ.name)
            if enum is not None and enum.underlying is not None:
                return self.ctype(enum.underlying)
            return "ctypes.c_int"

        if isinstance(typ, types.TypedefRef):
            return self(typ.name)

        if isinstance(typ, types.FunctionType):
            return self.function(typ)

        raise ValueError(f"no ctypes type for {typ!r}")

    def function(self, typ: types.FunctionType) -> str:
        """The ctypes type of a pointer to a function of type 'typ'"""

        args = [self.ctype(typ.ret)] + [self.ctype(p.typ, True) for p in typ.params]
        return f"ctypes.CFUNCTYPE({', '.join(args)})"

    def fields(self, record) -> List[str]:
        """The entries of the record's '_fields_'; of a blob, its bytes"""

        if self.is_blob(record):
            unit = BLOB_UNITS.get(record.align, "ctypes.c_uint64")
            count = record.size // min(record.align, 8)
            return [f'("_bits", {unit} * {count})']
        found = []
        for field in record.fields:
            entry = f'"{field.name}", {self.ctype(field.typ)}'
            if field.bits is not None:
                entry += f", {field.bits}"
            found.append(f"({entry})")
        return found


def returns(function: decls.Function, namer: Namer) -> str:
    """The helper converting what the wrapper of 'function' returns, if any"""

    if types.is_string(function.ret):
        return "_str_out"
    if namer.ctype(function.ret).startswith("ctypes.POINTER("):
        return "_ptr_out"
    return ""


def argument(param: decls.Param, name: str) -> str:
    """The expression passing the wrapper's argument 'name' on to C"""

    return f"_str_in({name})" if types.is_string(param.typ) else name


def params(function: decls.Function) -> List[str]:
    """The wrapper's parameter names; C allows unnamed ones, Python does not"""

    return [
        ident(p.name) if p.name else f"arg{i}" for i, p in enumerate(function.params)
    ]
