"""
C code for the IR: declarations of its types, and the statements of the pretty-
printers. The C target's templates lay out the files; this produces what goes in
them that depends on the types.
"""

import re
from typing import List, Optional

from yace.ir import decls, types
from yace.ir.cparser import CXX_KEYWORDS
from yace.ir.masks import VALUE_KEY
from yace.ir.model import Model


def param_name(name: str) -> str:
    """The name of a parameter in the generated header, which C++ includes too"""

    return f"{name}_" if name in CXX_KEYWORDS else name


def c_ident(text: str) -> str:
    return re.sub(r"[^0-9A-Za-z_]", "_", text)


def decl(typ, inner: str = "") -> str:
    """The C declaration of 'inner' as a 'typ', such as ``int *x``"""

    def join(base: str, inner: str) -> str:
        return f"{base} {inner}" if inner else base

    const = "const " if getattr(typ, "const", False) else ""

    if isinstance(typ, types.Builtin):
        return join(f"{const}{typ.name}", inner)
    if isinstance(typ, types.Record):
        return join(f"{const}{typ.tag} {typ.name}", inner)
    if isinstance(typ, types.EnumRef):
        return join(f"{const}enum {typ.name}", inner)
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
        return decl(typ.to, star)
    if isinstance(typ, types.Array):
        length = "" if typ.length is None else str(typ.length)
        return decl(typ.of, f"{inner}[{length}]")
    if isinstance(typ, types.FunctionType):
        params = ", ".join(decl(p.typ, param_name(p.name)) for p in typ.params)
        params = params or "void"
        if typ.variadic:
            params += ", ..."
        return decl(typ.ret, f"{inner}({params})")

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


class Printer(object):
    """The C statements printing a value of a type as JSON, one per line"""

    def __init__(self, model: Model):
        self.typedefs = model.typedefs()
        self.records = {name: r for name, r in model.records().items() if r.fields}

    def resolve(self, typ):
        """'typ', through typedefs declared in the IR"""

        while isinstance(typ, types.TypedefRef) and typ.name in self.typedefs:
            typ = self.typedefs[typ.name].typ
        return typ

    def record_of(self, typ) -> Optional[object]:
        typ = self.resolve(typ)
        if isinstance(typ, types.Record):
            return self.records.get(typ.name)
        return None

    def value(self, typ, expr: str, depth: int = 0) -> List[str]:
        typ = self.resolve(typ)
        out = 'wrtn += fprintf(stream, "{fmt}"{args});'

        if isinstance(typ, types.Builtin):
            name = typ.name
            if name == "bool":
                return [out.format(fmt="%s", args=f', {expr} ? "true" : "false"')]
            if name in ("float", "double"):
                return [out.format(fmt="%g", args=f", (double){expr}")]
            if (
                name.startswith("unsigned")
                or name.startswith("uint")
                or name == "size_t"
            ):
                return [out.format(fmt="%ju", args=f", (uintmax_t){expr}")]
            if name == "void":
                return [out.format(fmt="null", args="")]
            return [out.format(fmt="%jd", args=f", (intmax_t){expr}")]

        if isinstance(typ, types.EnumRef):
            return [out.format(fmt="%jd", args=f", (intmax_t){expr}")]

        if isinstance(typ, types.Pointer):
            if types.is_string(typ):
                return [f"wrtn += yace_pp_str(stream, {expr});"]
            # Straight to an integer: going through 'void *' is not allowed for a
            # function pointer, which a pointer to an external typedef may be
            return [f"wrtn += yace_pp_ptr(stream, (uintptr_t){expr});"]

        if isinstance(typ, types.Array):
            if typ.length is None:
                return [out.format(fmt="null", args="")]
            elem = self.resolve(typ.of)
            if isinstance(elem, types.Builtin) and elem.name == "char":
                return [f"wrtn += yace_pp_strn(stream, {expr}, {typ.length});"]
            idx = f"i{depth}"
            lines = [
                out.format(fmt="[", args=""),
                f"for (size_t {idx} = 0; {idx} < {typ.length}; ++{idx}) {{",
                f'\twrtn += fprintf(stream, "%s", {idx} ? ", " : "");',
            ]
            lines += [
                "\t" + line for line in self.value(elem, f"{expr}[{idx}]", depth + 1)
            ]
            lines += ["}", out.format(fmt="]", args="")]
            return lines

        if isinstance(typ, types.Record):
            if typ.name in self.records:
                return [f"wrtn += yace_pp_json_{typ.name}(stream, &{expr});"]
            return [out.format(fmt="null", args="")]

        return [out.format(fmt="null", args="")]

    def helpers(self, records) -> set:
        """The ``yace_pp_`` helpers the printers of 'records' call; clang warns of
        an unused static function, also an inline one"""

        text = "\n".join(
            "\n".join(self.json_body(r) + self.yaml_body(r)) for r in records
        )
        used = {name for name in ("str", "strn", "ptr") if f"yace_pp_{name}(" in text}
        if "str" in used:
            used.add("strn")
        return used

    def parts(self, field, expr: str, fmt: str, quote: str) -> List[str]:
        """The value of a field of bits and of each of its parts, as a mapping
        on one line, with the keys quoted by 'quote', the values by 'fmt'"""

        def key(name: str) -> str:
            return f"{quote}{name}{quote}"

        lines = [
            f'wrtn += fprintf(stream, "{{{key(VALUE_KEY)}: {fmt}", (uintmax_t){expr});'
        ]
        for mask in field.masks:
            part = f"(((uintmax_t){expr} & {mask.define}) >> {mask.lo})"
            lines.append(
                f'wrtn += fprintf(stream, ", {key(mask.name)}: {fmt}", {part});'
            )
        lines.append('wrtn += fprintf(stream, "}");')
        return lines

    def json_body(self, record) -> List[str]:
        lines = ["if (!obj) {", '\treturn fprintf(stream, "null");', "}", ""]
        lines.append('wrtn += fprintf(stream, "{");')
        named = [f for f in record.fields if f.name]  # not padding bit-fields
        for idx, field in enumerate(named):
            sep = ", " if idx else ""
            lines.append(f'wrtn += fprintf(stream, "{sep}\\"{field.name}\\": ");')
            if field.masks:
                lines += self.parts(field, f"obj->{field.name}", "%ju", '\\"')
                continue
            lines += self.value(field.typ, f"obj->{field.name}")
        lines.append('wrtn += fprintf(stream, "}");')
        return lines

    def yaml_body(self, record) -> List[str]:
        lines = []
        for field in (f for f in record.fields if f.name):
            nested = self.record_of(field.typ) if field.bits is None else None
            if nested is not None:
                lines.append(
                    f'wrtn += fprintf(stream, "%*s{field.name}:\\n", indent, "");'
                )
                lines.append(
                    f"wrtn += yace_pp_yaml_{nested.name}(stream, &obj->{field.name},"
                    " indent + 2);"
                )
                continue
            lines.append(f'wrtn += fprintf(stream, "%*s{field.name}: ", indent, "");')
            if field.masks:
                lines += self.parts(field, f"obj->{field.name}", "0x%jx", "")
            else:
                lines += self.value(field.typ, f"obj->{field.name}")
            lines.append('wrtn += fprintf(stream, "\\n");')
        return lines
