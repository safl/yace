# SPDX-FileCopyrightText: Simon A. F. Lund <os@safl.dk>
#
# SPDX-License-Identifier: GPL-2.0-only

"""
C code for the IR: declarations of its types, and the statements of the pretty-
printers. The C target's templates lay out the files; this produces what goes in
them that depends on the types.
"""

import re
from typing import Dict, List, Optional

from yace.ir import decls, types
from yace.ir.cparser import CXX_KEYWORDS
from yace.ir.model import Model


def param_name(name: str) -> str:
    """The name of a parameter in the generated header, which C++ includes too"""

    return f"{name}_" if name in CXX_KEYWORDS else name


def c_ident(text: str) -> str:
    return re.sub(r"[^0-9A-Za-z_]", "_", text)


def decl(typ, inner: str = "", spelled: Optional[Dict[str, str]] = None) -> str:
    """The C declaration of 'inner' as a 'typ', such as ``int *x``; a record or
    enum named in 'spelled' is spelled as it says, rather than by tag and name"""

    spelled = spelled or {}

    def join(base: str, inner: str) -> str:
        return f"{base} {inner}" if inner else base

    const = "const " if getattr(typ, "const", False) else ""

    if isinstance(typ, types.Builtin):
        return join(f"{const}{typ.name}", inner)
    if isinstance(typ, types.Record):
        name = spelled.get(typ.name, f"{typ.tag} {typ.name}")
        return join(f"{const}{name}", inner)
    if isinstance(typ, types.EnumRef):
        name = spelled.get(typ.name, f"enum {typ.name}")
        return join(f"{const}{name}", inner)
    if isinstance(typ, types.TypedefRef):
        return join(f"{const}{typ.name}", inner)
    if isinstance(typ, types.Pointer):
        star = (
            "*const " + inner
            if typ.const and inner
            else "*const" if typ.const else "*" + inner
        )
        if isinstance(typ.to, (types.Array, types.FunctionType)):
            star = f"({star})"
        return decl(typ.to, star, spelled)
    if isinstance(typ, types.Array):
        length = "" if typ.length is None else str(typ.length)
        return decl(typ.of, f"{inner}[{length}]", spelled)
    if isinstance(typ, types.FunctionType):
        params = ", ".join(decl(p.typ, param_name(p.name), spelled) for p in typ.params)
        params = params or "void"
        if typ.variadic:
            params += ", ..."
        return decl(typ.ret, f"{inner}({params})", spelled)

    raise ValueError(f"no C spelling for {typ!r}")


def field_decl(field: decls.Field) -> str:
    text = decl(field.typ, field.name)
    return f"{text} : {field.bits}" if field.bits is not None else text


def signature(function: decls.Function) -> str:
    """The function's declaration, with the return type on a line of its own"""

    params = ", ".join(decl(p.typ, param_name(p.name)) for p in function.params)
    params = params or "void"
    if function.variadic:
        params += ", ..."
    declarator = f"{function.name}({params})"

    mark = "\0"
    ret = decl(function.ret, mark)
    if ret.endswith(" " + mark):
        return f"{ret[:-2]}\n{declarator}"
    if ret.endswith("*" + mark):
        return f"{ret[:-1]}\n{declarator}"
    return decl(function.ret, declarator)


def pointer_type(function: decls.Function, spelled: Dict[str, str]) -> str:
    """The type of a pointer to 'function', as the headers spell its types"""

    params = ", ".join(decl(p.typ, "", spelled) for p in function.params) or "void"
    if function.variadic:
        params += ", ..."
    return decl(function.ret, f"(*)({params})", spelled)


def spellings(model: Model) -> Dict[str, str]:
    """The records and enums the headers spell other than by tag and name"""

    kinds = (decls.Struct, decls.Union, decls.Enum)
    return {
        e.name: e.spelled for e in model.entities if isinstance(e, kinds) and e.spelled
    }


def record_deps(record, model: Model) -> List[str]:
    """The records 'record' contains by value, which must be complete before it"""

    typedefs = model.typedefs()
    found = []

    def visit(typ):
        if isinstance(typ, types.Record):
            found.append(typ.name)
        elif isinstance(typ, types.Array):
            visit(typ.of)
        elif isinstance(typ, types.TypedefRef) and typ.name in typedefs:
            visit(typedefs[typ.name].typ)

    for field in record.fields:
        visit(field.typ)
    return found


def ordered_records(model: Model) -> list:
    """The records with fields, each after those it contains by value"""

    records = {
        e.name: e for e in model.entities if isinstance(e, decls.RECORDS) and e.fields
    }
    ordered: list = []
    seen: set = set()

    def visit(name, stack=()):
        if name in seen or name not in records or name in stack:
            return
        for dep in record_deps(records[name], model):
            visit(dep, stack + (name,))
        seen.add(name)
        ordered.append(records[name])

    for name in records:
        visit(name)
    return ordered


def tag(record) -> str:
    return "union" if isinstance(record, decls.Union) else "struct"


# The helpers that each helper calls, so that only the helpers used are generated
HELPER_DEPS = {
    "null": ("key", "eol"),
    "bool": ("key", "eol"),
    "int": ("key", "eol"),
    "uint": ("key", "eol"),
    "float": ("key", "eol"),
    "ptr": ("key", "eol"),
    "str": ("strn",),
    "strn": ("key", "eol"),
    "nest": ("key",),
    "list": ("key",),
    "list_end": ("eol",),
    "bits": ("key",),
    "bits_end": ("eol",),
}


class Printer(object):
    """The C statements printing the fields of a record, one call of a helper of
    the pretty-printers for each value, to the printing context ``pp``"""

    def __init__(self, model: Model):
        self.typedefs = model.typedefs()
        self.records = {name: r for name, r in model.records().items() if r.fields}

    def resolve(self, typ):
        """'typ', through typedefs declared in the IR"""

        while isinstance(typ, types.TypedefRef) and typ.name in self.typedefs:
            typ = self.typedefs[typ.name].typ
        return typ

    def value(
        self,
        typ,
        key: str,
        expr: str,
        pp: str = "pp",
        depth: int = 0,
        packed: bool = False,
    ) -> List[str]:
        """Statements printing 'expr' by 'key', a string literal, or NULL for an
        element of a list; of a field of a 'packed' record, a record is printed
        through a copy, as its address may not be aligned"""

        typ = self.resolve(typ)

        def call(helper: str, *args: str) -> List[str]:
            return [f"wrtn += yace_pp_{helper}(&{pp}, {', '.join((key,) + args)});"]

        if isinstance(typ, types.Builtin):
            name = typ.name
            if name == "bool":
                return call("bool", expr)
            if name in ("float", "double"):
                return call("float", f"(double){expr}")
            if (
                name.startswith("unsigned")
                or name.startswith("uint")
                or name == "size_t"
            ):
                return call("uint", f"(uintmax_t){expr}")
            if name == "void":
                return call("null")
            return call("int", f"(intmax_t){expr}")

        if isinstance(typ, types.EnumRef):
            return call("int", f"(intmax_t){expr}")

        if isinstance(typ, types.Pointer):
            if types.is_string(typ):
                return call("str", expr)
            # Straight to an integer: going through 'void *' is not allowed for a
            # function pointer, which a pointer to an external typedef may be
            return call("ptr", f"(uintptr_t){expr}")

        if isinstance(typ, types.Array):
            if typ.length is None:
                return call("null")
            elem = self.resolve(typ.of)
            if isinstance(elem, types.Builtin) and elem.name == "char":
                return call("strn", expr, str(typ.length))
            lst, idx = f"l{depth}", f"i{depth}"
            lines = [
                "{",
                f"\tstruct yace_pp {lst};",
                "",
                f"\twrtn += yace_pp_list(&{pp}, &{lst}, {key});",
                f"\tfor (size_t {idx} = 0; {idx} < {typ.length}; ++{idx}) {{",
            ]
            lines += [
                "\t\t" + line if line else line
                for line in self.value(
                    elem, "NULL", f"{expr}[{idx}]", lst, depth + 1, packed
                )
            ]
            lines += ["\t}", f"\twrtn += yace_pp_list_end(&{pp});", "}"]
            if depth:  # in the body of a loop, which is a block already
                return [line[1:] for line in lines[1:-1]]
            return lines

        if isinstance(typ, types.Record):
            if typ.name not in self.records:
                return call("null")
            nest = call("nest")
            if packed:
                local = f"v{depth}"
                return [
                    "{",
                    f"\tconst {typ.tag} {typ.name} {local} = {expr};",
                    "",
                    "\t" + nest[0],
                    f"\twrtn += yace_pp_rec_{typ.name}({pp}, &{local});",
                    "}",
                ]
            return nest + [f"wrtn += yace_pp_rec_{typ.name}({pp}, &{expr});"]

        return call("null")

    def body(self, record) -> List[str]:
        """The statements printing the named fields of 'record', at 'obj'"""

        named = [f for f in record.fields if f.name]  # not padding bit-fields
        if not named:
            return ["(void)obj;"]

        lines: List[str] = []
        for field in named:
            key, expr = f'"{field.name}"', f"obj->{field.name}"
            if not field.masks:
                lines += self.value(field.typ, key, expr, packed=record.packed)
                continue
            lines.append(f"wrtn += yace_pp_bits(&pp, {key}, (uintmax_t){expr});")
            for mask in field.masks:
                part = f"((uintmax_t){expr} & {mask.define}) >> {mask.lo}"
                lines.append(f'wrtn += yace_pp_part(&pp, "{mask.name}", {part});')
            lines.append("wrtn += yace_pp_bits_end(&pp);")
        return lines

    def helpers(self, records) -> set:
        """The helpers the printers of 'records' call; clang warns of an unused
        static function, also an inline one"""

        text = "\n".join("\n".join(self.body(r)) for r in records)
        found = set(re.findall(r"\byace_pp_(\w+)\(", text))
        used: set = set()
        todo = [name for name in found if not name.startswith("rec_")]
        while todo:
            name = todo.pop()
            if name not in used:
                used.add(name)
                todo += HELPER_DEPS.get(name, ())
        return used
