# SPDX-FileCopyrightText: Simon A. F. Lund <os@safl.dk>
#
# SPDX-License-Identifier: GPL-2.0-only

"""
The raw layer of the Go package declares the constants, enums, types and
functions of the C API under their C names, exported. Each C function is bound
as a Go function that calls it through cgo. A function cgo cannot call, such as
a variadic one, is not bound; a comment in its place says why.
"""

from typing import List, Optional

from yace.ir import decls, types
from yace.ir.model import Model
from yace.targets.capi import cgen
from yace.targets.idiom import typedefs_used

from .ggen import (
    GO_TYPES,
    IMPORTS,
    KEYWORDS,
    PREDECLARED,
    Namer,
    Records,
    Registry,
    align,
    comment,
    define_value,
    doc_lines,
    export,
    ident,
)


def param_names(names, reserved) -> List[str]:
    """Return the Go names of parameters by their C names, none 'reserved' or
    shared; one unnamed or '_' is 'arg<n>'"""

    registry = Registry(reserved)
    return [
        registry.add(ident(name) if name and name != "_" else f"arg{idx}")
        for idx, name in enumerate(names)
    ]


def doc(lines: List[str], *more: str) -> List[str]:
    """Return a doc comment of 'lines', with 'more' as a paragraph"""

    found = comment(lines)
    if found and more:
        found.append("//")
    return found + comment(list(more))


class Raw(object):
    """Renders the raw layer, whose names are registered first"""

    def __init__(self, model: Model, namer: Namer, records: Records):
        self.model = model
        self.namer = namer
        self.records = records
        self.prefix = cgen.c_ident(model.meta.prefix).upper()
        entities = model.entities
        self.enums = [e for e in entities if isinstance(e, decls.Enum)]
        self.functions = [e for e in entities if isinstance(e, decls.Function)]
        self.typedefs = [
            e
            for e in entities
            if isinstance(e, decls.Typedef) and e.name not in namer.aliases
        ]
        self.declared = [e for e in entities if isinstance(e, decls.RECORDS)]
        # namer.gotype() names the stubs, ahead of the constants and functions
        for entity in self.typedefs:
            namer.gotype(entity.typ)
        for record in self.declared:
            for field in record.fields:
                namer.gotype(field.typ)
        for function in self.functions:
            namer.gotype(function.ret)
            for param in function.params:
                namer.gotype(param.typ, True)
        registry = namer.registry
        self.constants = {
            e.name: registry.add(export(e.name))
            for e in entities
            if isinstance(e, decls.Define)
        }
        for enum in self.enums:
            for member in enum.members:
                self.constants[member.name] = registry.add(export(member.name))
        self.fn_names = {f.name: registry.add(export(f.name)) for f in self.functions}

    def reserved(self) -> set:
        """Return the names a body may use, which no parameter has"""

        return KEYWORDS | PREDECLARED | IMPORTS | self.namer.registry.taken

    def unbindable(self, function) -> Optional[str]:
        """Return why cgo cannot call 'function', if so"""

        if function.variadic:
            return "is variadic, which cgo cannot call"
        if function.name in KEYWORDS:
            return "is named as a Go keyword, which cgo cannot refer to"
        for typ in [function.ret] + [p.typ for p in function.params]:
            if not self.namer.by_value(typ):
                return (
                    f"takes or returns a {self.namer.gotype(typ)} by value, which"
                    " Go knows only the name of"
                )
            if self.unsized_pointee(typ):
                return (
                    "takes or returns a pointer to an array of no length, which cgo"
                    " cannot type"
                )
            named = [name for name in typedefs_used(typ) if name in KEYWORDS]
            if named:
                return (
                    f"uses the typedef '{named[0]}', named as a Go keyword, which"
                    " cgo cannot refer to"
                )
        return None

    def unsized_pointee(self, typ) -> bool:
        """Return whether 'typ' holds a pointer to an unsized array"""

        typ = self.namer.resolve(typ)
        if isinstance(typ, types.Pointer):
            to = self.namer.resolve(typ.to)
            if isinstance(to, types.Array) and to.length is None:
                return True
            return self.unsized_pointee(to)
        if isinstance(typ, types.Array):
            return self.unsized_pointee(typ.of)
        if isinstance(typ, types.FunctionType):
            return any(
                self.unsized_pointee(t) for t in [typ.ret, *(p.typ for p in typ.params)]
            )
        return False

    def define(self, entity) -> List[str]:
        return (
            [""]
            + comment(doc_lines(entity.doc))
            + [f"const {self.constants[entity.name]} = {define_value(entity.value)}"]
        )

    def enum(self, entity) -> List[str]:
        name = self.namer.type_name(types.EnumRef(name=entity.name))
        under = GO_TYPES[entity.underlying.name] if entity.underlying else "int32"
        lines = [""] + doc(
            doc_lines(entity.doc),
            f"{name} is an integer, because C does not restrict a value to the",
            "named ones.",
        )
        lines.append(f"type {name} {under}")
        rows = []
        for member in entity.members:
            docs = [" ".join(member.doc.brief.split())] if member.doc.brief else []
            rows.append(
                (docs, [self.constants[member.name], name, f"= {member.value}"])
            )
        if rows:
            lines += ["", "const ("] + align(rows) + [")"]
        lines += [
            "",
            "// Name returns the C name of the value, and false when it has none",
            f"func (v {name}) Name() (string, bool) {{",
        ]
        cases = []
        seen = set()
        for member in entity.members:
            if member.value not in seen:
                seen.add(member.value)
                cases += [
                    f"\tcase {self.constants[member.name]}:",
                    f'\t\treturn "{member.name}", true',
                ]
        if cases:
            lines += ["\tswitch v {"] + cases + ["\t}"]
        unsigned = under.startswith("u") or under == "CULong"
        text = (
            "strconv.FormatUint(uint64(v), 10)"
            if unsigned
            else "strconv.FormatInt(int64(v), 10)"
        )
        lines += [
            '\treturn "", false',
            "}",
            "",
            f"// String returns the C name of the value, or {name}(<value>)",
            f"func (v {name}) String() string {{",
            "\tif name, ok := v.Name(); ok {",
            "\t\treturn name",
            "\t}",
            f'\treturn "{name}(" + {text} + ")"',
            "}",
        ]
        return lines

    def typedef(self, entity) -> List[str]:
        name = self.namer.type_name(types.TypedefRef(name=entity.name))
        lines = [""] + comment(doc_lines(entity.doc))
        if isinstance(entity.typ, types.Pointer) and self.namer.is_function_ptr(
            entity.typ
        ):
            return lines + [f"type {name} unsafe.Pointer"]
        return lines + [f"type {name} = {self.namer.gotype(entity.typ)}"]

    def stub(self, cname: str, name: str) -> List[str]:
        return [
            "",
            f"// {name} is '{cname}', declared outside the headers; usable only",
            "// through pointers",
            f"type {name} struct{{ _ [0]byte }}",
        ]

    def record(self, record) -> List[str]:
        name = self.namer.type_name(types.Record(tag="struct", name=record.name))
        lines = [""] + self.records.declare(record, name)
        if record.packed and not self.records.is_blob(record):
            lines += self.records.packed_fields(record, name)
        elif isinstance(record, decls.Union) and not self.records.is_blob(record):
            lines += self.records.members(record, name)
        lines += self.records.printers(record, name, self.prefix)
        lines += self.records.accessors(record, name)
        return lines

    def function(self, function) -> List[str]:
        name = self.fn_names[function.name]
        names = param_names(
            [p.name for p in function.params], self.reserved() | {"ret"}
        )
        renamed = dict(zip([p.name for p in function.params], names))
        shown = function.doc.model_copy(
            update={
                "params": {
                    renamed[k]: v
                    for k, v in function.doc.params.items()
                    if k in renamed
                }
            }
        )
        reason = self.unbindable(function)
        if reason:
            return [""] + doc(
                doc_lines(shown),
                f"{name} is not bound: {function.name}() {reason}.",
            )
        lines = [""] + doc(doc_lines(shown), f"{name} calls {function.name}.")
        sig = ", ".join(
            f"{n} {self.namer.gotype(p.typ, True)}"
            for n, p in zip(names, function.params)
        )
        ret = self.namer.gotype(function.ret)
        args = ", ".join(
            self.namer.to_c(p.typ, n) for n, p in zip(names, function.params)
        )
        call = f"C.{function.name}({args})"
        kind = self.namer.kind(function.ret)
        lines.append(f"func {name}({sig}){' ' + ret if ret else ''} {{")
        if kind == "none":
            lines.append(f"\t{call}")
        elif kind == "record":
            lines.append(f"\tret := {call}")
            lines.append(f"\treturn {self.namer.from_c(function.ret, 'ret')}")
        else:
            lines.append(f"\treturn {self.namer.from_c(function.ret, call)}")
        lines.append("}")
        return lines

    def render(self) -> List[str]:
        """Return the lines of the raw layer"""

        lines: List[str] = []
        for entity in self.model.entities:
            if isinstance(entity, decls.Define):
                lines += self.define(entity)
        for entity in self.enums:
            lines += self.enum(entity)
        for cname, name in sorted(self.namer.stubs.items()):
            lines += self.stub(cname, name)
        for record in self.declared:
            lines += self.record(record)
        for entity in self.typedefs:
            lines += self.typedef(entity)
        for function in self.functions:
            lines += self.function(function)
        return lines
