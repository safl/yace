"""
Cython code for the IR: the names of the C API in a ``.pxd``, and the Cython
spelling of each IR type. The ``.pxd`` declares the C API as the C target's
header does, so Cython code cimports it and calls C directly; the check, a
``.pyx`` cimporting every name, holds each declaration to the header.
"""

import keyword
from typing import Dict, List

from yace.ir import decls, types
from yace.ir.model import Model
from yace.targets.capi import cgen

# What Cython reserves beyond Python's keywords, which a name in a .pxd may not
# be; such a C name is declared under another, its C name given as a string
RESERVED = {
    "DEF",
    "ELIF",
    "ELSE",
    "IF",
    "NULL",
    "Py_UCS4",
    "Py_UNICODE",
    "Py_hash_t",
    "Py_ssize_t",
    "api",
    "bint",
    "by",
    "cdef",
    "cimport",
    "cpdef",
    "cppclass",
    "ctypedef",
    "extern",
    "fused",
    "gil",
    "include",
    "namespace",
    "new",
    "noexcept",
    "nogil",
    "object",
    "operator",
    "print",
    "public",
    "readonly",
    "sizeof",
    "typeof",
}

# The builtins Cython does not know by their C names, and where they are
CIMPORTS = {
    "libc.stdint": [
        "int8_t",
        "int16_t",
        "int32_t",
        "int64_t",
        "uint8_t",
        "uint16_t",
        "uint32_t",
        "uint64_t",
        "intptr_t",
        "uintptr_t",
    ],
    "libc.stddef": ["ptrdiff_t"],
}

# The C 'bool', which Cython knows as 'bint', an int; declared as C's own name
# for it, so what Cython declares of it is a bool
BOOL = "_Bool"


def reserved(name: str) -> bool:
    return keyword.iskeyword(name) or name in RESERVED


class Names(object):
    """The names of the C API in the .pxd: the C names, but for those Cython
    reserves, and the tags of records and enums that share a name with
    something else, as C keeps tags apart and Cython does not"""

    def __init__(self, model: Model):
        self.model = model
        self.records = model.records()
        self.enums = model.enums()
        self.typedefs = model.typedefs()
        # A typedef of the record or enum of its own name is that type
        self.aliases = {
            name
            for name, typedef in self.typedefs.items()
            if isinstance(typedef.typ, (types.Record, types.EnumRef))
            and typedef.typ.name == name
        }
        # Types used but declared outside the headers, by tag or typedef name
        self.stub_tags: Dict[str, str] = {}
        self.stub_types: Dict[str, str] = {}
        self.kinds: Dict[str, str] = {}  # 'struct', 'union' or 'enum', by tag

        ordinary = [e.name for e in model.entities if isinstance(e, decls.Function)]
        ordinary += [e.name for e in model.entities if isinstance(e, decls.Define)]
        ordinary += [m.name for e in self.enums.values() for m in e.members]
        ordinary += [n for n in self.typedefs if n not in self.aliases]
        self.taken = set(ordinary)
        self.names = {name: self.unique(name, own=True) for name in ordinary}
        self.tags = {name: self.unique(name) for name in [*self.enums, *self.records]}

    def unique(self, name: str, own: bool = False) -> str:
        """'name', or with '_' until it is neither reserved nor taken by another;
        an 'own' name is taken by itself"""

        if not reserved(name) and (own or name not in self.taken):
            self.taken.add(name)
            return name
        found = f"{name}_"
        while reserved(found) or found in self.taken:
            found += "_"
        self.taken.add(found)
        return found

    def cname(self, name: str, cname: str) -> str:
        """'name' as declared in the .pxd, with its C name where that differs"""

        return name if name == cname else f'{name} "{cname}"'

    def of(self, name: str) -> str:
        """The .pxd name of the function, typedef, define or enum member 'name'"""

        return self.names.get(name, name)

    def tag(self, name: str) -> str:
        """The .pxd name of the record or enum 'name'"""

        if name in self.tags:
            return self.tags[name]
        if name not in self.stub_tags:
            self.stub_tags[name] = self.unique(name)
        return self.stub_tags[name]

    def resolve(self, typ):
        while isinstance(typ, types.TypedefRef) and typ.name in self.typedefs:
            typ = self.typedefs[typ.name].typ
        return typ

    def typedef(self, name: str) -> str:
        """The .pxd name of the typedef 'name', or of the type it aliases"""

        if name in self.aliases:
            return self.tag(name)
        if name in self.typedefs:
            return self.of(name)
        if name not in self.stub_types:
            self.stub_types[name] = self.unique(name)
        return self.stub_types[name]

    def decl(self, typ, inner: str = "", qual: str = "", spec: str = "") -> str:
        """The Cython declaration of 'inner' as a 'typ'; with 'qual', such as
        'c.', the names of the API are those of the .pxd cimported as it, and
        'spec', such as 'noexcept', follows each function type"""

        def join(base: str, inner: str) -> str:
            return f"{base} {inner}" if inner else base

        const = "const " if getattr(typ, "const", False) else ""

        if isinstance(typ, types.Builtin):
            name = f"{qual}{BOOL}" if typ.name == "bool" else typ.name
            return join(f"{const}{name}", inner)
        if isinstance(typ, types.Record):
            self.kinds.setdefault(typ.name, typ.tag)
            return join(f"{const}{qual}{self.tag(typ.name)}", inner)
        if isinstance(typ, types.EnumRef):
            self.kinds.setdefault(typ.name, "enum")
            return join(f"{const}{qual}{self.tag(typ.name)}", inner)
        if isinstance(typ, types.TypedefRef):
            return join(f"{const}{qual}{self.typedef(typ.name)}", inner)
        if isinstance(typ, types.Pointer):
            star = ("*const " if typ.const else "*") + inner
            star = star.rstrip()
            if isinstance(typ.to, (types.Array, types.FunctionType)):
                star = f"({star})"
            return self.decl(typ.to, star, qual, spec)
        if isinstance(typ, types.Array):
            length = "" if typ.length is None else str(typ.length)
            return self.decl(typ.of, f"{inner}[{length}]", qual, spec)
        if isinstance(typ, types.FunctionType):
            params = ", ".join(self.decl(p.typ, "", qual, spec) for p in typ.params)
            if typ.variadic:
                params += ", ..."
            spec = f" {spec}" if spec else ""
            return self.decl(typ.ret, f"{inner}({params}){spec}", qual, spec.strip())

        raise ValueError(f"no Cython spelling for {typ!r}")


def spelled_function(typ) -> bool:
    """Whether 'typ' spells out a function type, rather than by a typedef"""

    while isinstance(typ, (types.Pointer, types.Array)):
        typ = typ.to if isinstance(typ, types.Pointer) else typ.of
    return isinstance(typ, types.FunctionType)


def field_name(name: str) -> str:
    """The .pxd name of a field, in the namespace of its record"""

    return f"{name}_" if reserved(name) else name


def param_name(name: str) -> str:
    return f"{name}_" if reserved(name) else name


class Pxd(object):
    """The declarations of the .pxd, in the order the C target's header has
    them: enums, records declared, typedefs, records defined, functions"""

    def __init__(self, model: Model):
        self.model = model
        self.names = Names(model)

    def define(self, entity: decls.Define) -> str:
        name = self.names.cname(self.names.of(entity.name), entity.name)
        if isinstance(entity.value, decls.StrLiteral):
            return f"const char *{name}"
        if entity.value.value > 2**63 - 1:
            return f"const unsigned long long {name}"
        return f"const long long {name}"

    def enum(self, entity: decls.Enum) -> List[str]:
        name = self.names.tag(entity.name)
        lines = [f"enum {self.names.cname(name, entity.name)}:"]
        for member in entity.members:
            lines.append(
                f"    {self.names.cname(self.names.of(member.name), member.name)}"
            )
        return lines

    def record(self, record, complete: bool) -> List[str]:
        name = self.names.tag(record.name)
        tag = cgen.tag(record)
        head = f"{tag} {self.names.cname(name, record.name)}"
        if not complete:
            return [head]
        # Cython has no packed union
        packed = "packed " if record.packed and tag == "struct" else ""
        lines = [f"{packed}{head}:"]
        for field in record.fields:
            if not field.name:
                continue  # padding bits, which C names nothing
            fname = self.names.cname(field_name(field.name), field.name)
            typ = field.typ
            if isinstance(typ, types.Array) and typ.length is None:
                lines.append(
                    f"    # {field.name}[], a flexible array, is left out:"
                    " Cython has none"
                )
                continue
            lines.append(f"    {self.names.decl(typ, fname)}")
        return lines

    def typedef(self, entity: decls.Typedef) -> str:
        name = self.names.cname(self.names.of(entity.name), entity.name)
        return f"ctypedef {self.names.decl(entity.typ, name)}"

    def function(self, function: decls.Function) -> str:
        params = [self.names.decl(p.typ, param_name(p.name)) for p in function.params]
        if function.variadic:
            params.append("...")
        name = self.names.cname(self.names.of(function.name), function.name)
        return self.names.decl(function.ret, f"{name}({', '.join(params)})")

    def lines(self) -> List[str]:
        """The declarations, indented for the 'cdef extern' block"""

        entities = self.model.entities
        complete = cgen.ordered_records(self.model)
        records = [e for e in entities if isinstance(e, decls.RECORDS)]
        typedefs = [
            e
            for e in entities
            if isinstance(e, decls.Typedef) and e.name not in self.names.aliases
        ]
        body: List[str] = []
        for entity in entities:
            if isinstance(entity, decls.Define):
                body.append(self.define(entity))
        for entity in entities:
            if isinstance(entity, decls.Enum):
                body += self.enum(entity)
        for record in records:
            body += self.record(record, False)
        for entity in typedefs:
            body.append(self.typedef(entity))
        for record in complete:
            body += self.record(record, True)
        for entity in entities:
            if isinstance(entity, decls.Function):
                body.append(self.function(entity))

        # Types used but declared outside the headers, such as FILE, known only
        # by name, so usable only through pointers
        stubs = [f"ctypedef bint {BOOL}"]
        for cname, name in sorted(self.names.stub_types.items()):
            stubs += [f"ctypedef struct {self.names.cname(name, cname)}:", "    pass"]
        for cname, name in sorted(self.names.stub_tags.items()):
            kind = self.names.kinds.get(cname, "struct")
            if kind == "enum":
                stubs += [f"enum {self.names.cname(name, cname)}:", "    pass"]
            else:
                stubs.append(f"{kind} {self.names.cname(name, cname)}")
        return stubs + body


class Check(object):
    """The body of a function, never called, assigning each name the .pxd
    declares, cimported as 'c', to what Cython takes its type to be, or its
    address to a pointer to that; the C compiler, given the header, then fails
    where a declaration disagrees with it"""

    def __init__(self, pxd: Pxd):
        self.pxd = pxd
        self.names = pxd.names
        self.cdefs: List[str] = []
        self.assigned: List[str] = []

    def local(self, typ, value: str = "", spec: str = "noexcept nogil") -> str:
        """A local of 'typ' assigned 'value'; a function type it holds has
        'spec', as Cython gives what the .pxd declares of the C API, but for a
        field of a function pointer, which it does not declare nogil"""

        # Assigned apart, as Cython does not initialize a function pointer
        name = f"v{len(self.cdefs)}"
        self.cdefs.append(f"cdef {self.names.decl(typ, name, 'c.', spec)}")
        if value:
            self.assigned.append(f"{name} = {value}")
        return name

    def render(self) -> List[str]:
        names = self.names
        model = self.pxd.model
        for entity in model.entities:
            if isinstance(entity, decls.Define):
                value = f"c.{names.of(entity.name)}"
                if isinstance(entity.value, decls.StrLiteral):
                    char = types.Builtin(name="char", const=True)
                    self.local(types.Pointer(to=char), value)
                elif entity.value.value > 2**63 - 1:
                    self.local(types.Builtin(name="unsigned long long"), value)
                else:
                    self.local(types.Builtin(name="long long"), value)
            elif isinstance(entity, decls.Enum):
                enum = types.EnumRef(name=entity.name)
                for each in entity.members:
                    self.local(enum, f"c.{names.of(each.name)}")
            elif isinstance(entity, decls.Typedef):
                if entity.name not in names.aliases:
                    if isinstance(entity.typ, types.Pointer):
                        # Cython spells no pointer to a function pointer
                        made = self.local(types.TypedefRef(name=entity.name), "NULL")
                        self.local(entity.typ, made)
                    else:
                        made = self.local(types.TypedefRef(name=entity.name))
                        self.local(types.Pointer(to=entity.typ), f"&{made}")
            elif isinstance(entity, decls.Function):
                fn = types.FunctionType(
                    ret=entity.ret,
                    params=[types.TypeParam(typ=p.typ) for p in entity.params],
                    variadic=entity.variadic,
                )
                self.local(types.Pointer(to=fn), f"c.{names.of(entity.name)}")

        for record in cgen.ordered_records(model):
            made = self.local(types.Record(tag=cgen.tag(record), name=record.name))
            for field in record.fields:
                flexible = (
                    isinstance(field.typ, types.Array) and field.typ.length is None
                )
                if not field.name or flexible:
                    continue
                member = f"{made}.{field_name(field.name)}"
                spec = "noexcept" if spelled_function(field.typ) else "noexcept nogil"
                if field.bits is not None:
                    self.local(field.typ, member)  # a bit-field has no address
                elif record.packed:
                    # The address of a packed field may not be aligned, so a
                    # copy of it, of an array its first element, is assigned
                    typ = field.typ
                    while isinstance(typ, types.Array):
                        typ, member = typ.of, f"{member}[0]"
                    self.local(typ, member, spec)
                else:
                    self.local(types.Pointer(to=field.typ), f"&{member}", spec)
        for record in model.records().values():
            if not record.fields:
                opaque = types.Record(tag=cgen.tag(record), name=record.name)
                self.local(types.Pointer(to=opaque), "NULL")
        return self.cdefs + self.assigned
