"""
The idiomatic C++ layer of the API, over the C API the C target generates,
which is its raw layer, as C++ includes C headers: handles as move-only RAII
classes, errors as ``std::system_error``, what is written through ``[out]``
pointers returned, ``std::span`` for arrays, ``std::vector`` for those
returned, ``std::string_view`` for strings, ``std::optional`` where NULL is
allowed, and any callable for callbacks. See :py:mod:`yace.targets.idiom` for
what is derived from where.

Everything is in a namespace named for the prefix, its names without it, so
nothing clashes with the macros of the C API's ``#define`` constants; where the
C API has a declaration named as the prefix, the namespace is the prefix and
``_cpp``.
"""

from functools import cached_property
from typing import Dict, List, Optional, Tuple

from yace.ir import decls, types
from yace.ir.masks import VALUE_KEY
from yace.ir.semantics import is_void_ptr
from yace.targets.capi import cgen
from yace.targets.capi.target import comment as uncommented
from yace.targets.idiom import (
    Arg,
    Call,
    Idioms,
    copyable,
    is_opaque_ptr,
    local,
    strip,
    typedefs_used,
)

KEYWORDS = set(
    "alignas alignof and and_eq asm auto bitand bitor bool break case catch char"
    " char8_t char16_t char32_t class compl concept const consteval constexpr"
    " constinit const_cast continue co_await co_return co_yield decltype default"
    " delete do double dynamic_cast else enum explicit export extern false float"
    " for friend goto if inline int long mutable namespace new noexcept not not_eq"
    " nullptr operator or or_eq private protected public register reinterpret_cast"
    " requires return short signed sizeof static static_assert static_cast struct"
    " switch template this thread_local throw true try typedef typeid typename"
    " union unsigned using virtual void volatile wchar_t while xor xor_eq".split()
)


# What the namespace declares or names unqualified: printers and helpers
RESERVED = {"yaml", "json", "name", "detail", "std"}


def ident(name: str) -> str:
    """'name' usable in C++, and other than 'ret', the local of the result"""

    return f"{name}_" if name in KEYWORDS or name == "ret" else name


def comment(doc, indent: str = "") -> List[str]:
    """'doc', without its parameters, as a Doxygen comment"""

    lines = []
    if doc.brief:
        lines.append(doc.brief)
    for para in [p for p in doc.description.split("\n\n") if p]:
        lines += ["", para]
    if doc.returns:
        lines += ["", f"@return {doc.returns}"]
    if not lines:
        return []
    body = [f"{indent} * {uncommented(line)}".rstrip() for line in lines]
    return [f"{indent}/**"] + body + [f"{indent} */"]


HELPERS = r"""inline void
put_int(std::string &out, std::intmax_t value)
{
	out += std::to_string(value);
}

inline void
put_uint(std::string &out, std::uintmax_t value)
{
	out += std::to_string(value);
}

inline void
put_hex(std::string &out, std::uintmax_t value)
{
	char buf[32];
	int len = std::snprintf(buf, sizeof(buf), "0x%jx", value);
	out.append(buf, static_cast<std::size_t>(len));
}

/// 'value' as printf() prints it with "%g", by C's own, so they agree
inline void
put_g(std::string &out, double value)
{
	char buf[32];
	int len = std::snprintf(buf, sizeof(buf), "%g", value);
	out.append(buf, static_cast<std::size_t>(len));
}

inline void
put_strn(std::string &out, const char *str, std::size_t len)
{
	if (!str) {
		out += "null";
		return;
	}
	out += '"';
	for (std::size_t i = 0; i < len && str[i]; ++i) {
		auto chr = static_cast<unsigned char>(str[i]);
		if (chr == '"' || chr == '\\') {
			out += '\\';
			out += static_cast<char>(chr);
		} else if (chr < 0x20 || chr == 0x7f) {
			char buf[8];
			std::snprintf(buf, sizeof(buf), "\\u%04x", chr);
			out += buf;
		} else {
			out += static_cast<char>(chr);
		}
	}
	out += '"';
}

inline void
put_str(std::string &out, const char *str)
{
	put_strn(out, str, SIZE_MAX);
}

inline void
put_ptr(std::string &out, std::uintptr_t addr)
{
	if (!addr) {
		out += "null";
		return;
	}
	out += '"';
	put_hex(out, addr);
	out += '"';
}""".splitlines()


def copied(expr: str, local: str, call: str) -> List[str]:
    """The statement 'call', formatted with a local, on a copy of 'expr' in it"""

    return ["{", f"\tconst auto {local} = {expr};", f"\t{call.format(local)};", "}"]


class Printer(object):
    """The C++ statements printing a value of a type into the std::string
    'out', as the pretty-printers of the C API print it"""

    def __init__(self, model):
        self.typedefs = model.typedefs()
        self.records = {name: r for name, r in model.records().items() if r.fields}

    def resolve(self, typ):
        while isinstance(typ, types.TypedefRef) and typ.name in self.typedefs:
            typ = self.typedefs[typ.name].typ
        return typ

    def named(self, record) -> list:
        """The fields printed: those with a name, not padding bit-fields"""

        return [f for f in record.fields if f.name]

    def value(self, typ, expr: str, depth: int = 0, packed: bool = False) -> List[str]:
        """Statements printing 'expr'; of a field of a 'packed' record, a record
        is printed through a copy, as a reference to it may not be aligned"""

        typ = self.resolve(typ)
        null = ['out += "null";']

        if isinstance(typ, types.Builtin):
            name = typ.name
            if name == "bool":
                return [f'out += {expr} ? "true" : "false";']
            if name in ("float", "double"):
                return [f"detail::put_g(out, static_cast<double>({expr}));"]
            if name.startswith(("unsigned", "uint")) or name == "size_t":
                return [f"detail::put_uint(out, static_cast<std::uintmax_t>({expr}));"]
            if name == "void":
                return null
            return [f"detail::put_int(out, static_cast<std::intmax_t>({expr}));"]

        if isinstance(typ, types.EnumRef):
            return [f"detail::put_int(out, static_cast<std::intmax_t>({expr}));"]

        if isinstance(typ, types.Pointer):
            if types.is_string(typ):
                return [f"detail::put_str(out, {expr});"]
            return [f"detail::put_ptr(out, reinterpret_cast<std::uintptr_t>({expr}));"]

        if isinstance(typ, types.Array):
            if typ.length is None:
                return null
            elem = self.resolve(typ.of)
            if isinstance(elem, types.Builtin) and elem.name == "char":
                return [f"detail::put_strn(out, {expr}, {typ.length});"]
            idx = f"i{depth}"
            lines = [
                "out += '[';",
                f"for (std::size_t {idx} = 0; {idx} < {typ.length}; ++{idx}) {{",
                f'\tout += {idx} ? ", " : "";',
            ]
            lines += [
                "\t" + line
                for line in self.value(elem, f"{expr}[{idx}]", depth + 1, packed)
            ]
            return lines + ["}", "out += ']';"]

        if isinstance(typ, types.Record) and typ.name in self.records:
            if packed:
                return copied(expr, f"v{depth}", "detail::json(out, {})")
            return [f"detail::json(out, {expr});"]

        return null

    def record_of(self, typ):
        typ = self.resolve(typ)
        if isinstance(typ, types.Record):
            return self.records.get(typ.name)
        return None

    def parts(self, field, expr: str, put: str, quote: str) -> List[str]:
        """The value of a field of bits and of each of its parts, as a mapping
        on one line, with the keys quoted by 'quote', the values put by 'put'"""

        value = f"static_cast<std::uintmax_t>({expr})"
        lines = [
            f'out += "{{{quote}{VALUE_KEY}{quote}: ";',
            f"detail::{put}(out, {value});",
        ]
        for mask in field.masks:
            lines += [
                f'out += ", {quote}{mask.name}{quote}: ";',
                f"detail::{put}(out, ({value} & {mask.value:#x}u) >> {mask.lo});",
            ]
        return lines + ["out += '}';"]

    def json_body(self, record) -> List[str]:
        lines = ["out += '{';"]
        for idx, field in enumerate(self.named(record)):
            sep = ", " if idx else ""
            lines.append(f'out += "{sep}\\"{field.name}\\": ";')
            if field.masks:
                lines += self.parts(field, f"obj.{field.name}", "put_uint", '\\"')
            else:
                lines += self.value(
                    field.typ, f"obj.{field.name}", packed=record.packed
                )
        return lines + ["out += '}';"]

    def yaml_body(self, record) -> List[str]:
        lines = []
        for field in self.named(record):
            lines.append("out.append(static_cast<std::size_t>(indent), ' ');")
            nested = self.record_of(field.typ) if field.bits is None else None
            if nested is not None:
                lines.append(f'out += "{field.name}:\\n";')
                call = "detail::yaml(out, {}, indent + 2)"
                if record.packed:
                    lines += copied(f"obj.{field.name}", "v0", call)
                else:
                    lines.append(f"{call.format('obj.' + field.name)};")
                continue
            lines.append(f'out += "{field.name}: ";')
            if field.masks:
                lines += self.parts(field, f"obj.{field.name}", "put_hex", "")
            else:
                lines += self.value(
                    field.typ, f"obj.{field.name}", packed=record.packed
                )
            lines.append("out += '\\n';")
        return lines


class Renderer(object):
    def __init__(self, model):
        self.model = model
        self.idioms = Idioms(model)
        self.prefix = model.meta.prefix
        self.typedefs = model.typedefs()
        self.c_names = {getattr(e, "name", None) for e in model.entities}
        ns = cgen.c_ident(self.prefix)
        taken = {getattr(e, "name", None) for e in model.entities}
        self.ns = f"{ns}_cpp" if ns in taken else ns
        self.classes = [
            name for name in self.idioms.handles if any(self.idioms.of(name).values())
        ]

    def name(self, cname: str) -> str:
        """The name in the namespace: without the prefix; one that would hide a
        C name the generated code uses, its own struct's for a handle's class,
        is suffixed"""

        name = strip(cname, self.prefix)
        other = name != cname and name in self.c_names or name in RESERVED
        if cname in self.idioms.handles and (name == cname or other):
            name += "_handle"
        elif other:
            name += "_"
        return ident(name)

    def c(self, typ, inner: str = "") -> str:
        """The C declaration of 'inner' as a 'typ', from C++: its names
        qualified, as one the namespace declares, such as an enum class, would
        be found first"""

        def qualified(typ):
            if isinstance(typ, (types.Record, types.EnumRef, types.TypedefRef)):
                return typ.model_copy(update={"name": f"::{typ.name}"})
            if isinstance(typ, types.Pointer):
                return typ.model_copy(update={"to": qualified(typ.to)})
            if isinstance(typ, types.Array):
                return typ.model_copy(update={"of": qualified(typ.of)})
            if isinstance(typ, types.FunctionType):
                params = [
                    p.model_copy(update={"typ": qualified(p.typ)}) for p in typ.params
                ]
                return typ.model_copy(
                    update={"ret": qualified(typ.ret), "params": params}
                )
            return typ

        return cgen.decl(qualified(typ), inner)

    def callback(self, typ) -> Optional[types.FunctionType]:
        while isinstance(typ, types.TypedefRef) and typ.name in self.typedefs:
            typ = self.typedefs[typ.name].typ
        if isinstance(typ, types.Pointer) and isinstance(typ.to, types.FunctionType):
            return typ.to
        return None

    def param_type(self, arg: Arg) -> Optional[str]:
        typ = arg.typ
        if arg.kind == "string":
            return "const char *" if arg.nullable else "const std::string &"
        if arg.kind == "sequence":
            return f"std::span<{self.elem(typ.to)}>"
        if arg.kind == "callback":
            return "F &&"
        if arg.kind == "capacity":
            return self.c(typ)
        if arg.kind != "value":
            return None
        handle = is_opaque_ptr(typ, self.idioms.handles)
        if handle in self.classes:
            cls = self.name(handle)
            return f"const {cls} *" if arg.nullable else f"const {cls} &"
        if (
            isinstance(typ, types.Pointer)
            and not is_void_ptr(typ)
            and isinstance(typ.to, (types.Record, types.Builtin))
            and not arg.nullable
        ):
            return f"{self.c(typ.to)} &"
        return self.c(typ)

    def elem(self, typ) -> str:
        """The C++ type of an element of an array, std::byte for void"""

        if isinstance(typ, types.Builtin) and typ.name == "void":
            return "const std::byte" if typ.const else "std::byte"
        return self.c(typ)

    @cached_property
    def reserved(self) -> set:
        """What a body names unqualified: the result, std, the namespace's
        helpers, C names, among them typedefs from other headers, and its
        classes"""

        classes = {self.name(c) for c in self.classes}
        used = set(typedefs_used(self.model.entities))
        return {"ret", "std", "detail"} | self.c_names | used | classes

    def pname(self, name: str) -> str:
        """A parameter's name, other than a keyword or a name the body uses; one
        ending in '_' gets another, so no two parameters, and no member such as
        ptr_, share a name"""

        if name in KEYWORDS or name in self.reserved or name.endswith("_"):
            return f"{name}_"
        return name

    def local(self, call: Call, param: str, suffix: str) -> str:
        """The local made for 'param', other than the name of a parameter or of
        what the body names unqualified"""

        taken = {self.pname(a.param) for a in call.args} | self.reserved
        return local(self.pname(param), suffix, taken)

    def tparam(self, call: Call, arg: Arg) -> str:
        """The template parameter of the callable given for a callback, other
        than the names of the call's parameters, of the handle classes, of the
        C names, of the call itself and of the methods of its class, which an
        out-of-class definition finds first"""

        callbacks = [a for a in call.args if a.kind == "callback"]
        taken = {self.pname(a.param) for a in call.args}
        taken |= {self.name(c) for c in self.classes} | self.c_names
        taken |= {self.fn_name(call), self.method_name(call)}
        taken |= {
            self.method_name(c)
            for c in self.idioms.calls
            if c.handle == call.handle and c.kind in ("method", "destructor")
        }
        stem = "F"
        while True:
            names = (
                [stem]
                if len(callbacks) == 1
                else [f"{stem}{i}" for i in range(len(callbacks))]
            )
            if not taken & set(names):
                return names[callbacks.index(arg)]
            stem += "_"

    def nulled(self, call: Call, arg: Arg) -> bool:
        """Whether 'arg' is a nullable callback, or its context"""

        if arg.kind == "context":
            arg = next(a for a in call.args if a.param == arg.of)
        return arg.kind == "callback" and arg.nullable

    def param_expr(self, call: Call, arg: Arg, null: bool = False) -> str:
        name = self.pname(arg.param)
        if null and self.nulled(call, arg):
            return "nullptr"
        if arg.kind == "self":
            return "ptr_.get()"
        if arg.kind == "string":
            return name if arg.nullable else f"{name}.c_str()"
        if arg.kind == "sequence":
            return f"{name}.data()"
        if arg.kind == "length":
            return f"{self.pname(arg.of)}.size()"
        if arg.kind == "out":
            out = next(o for o in call.outs if o.param == arg.param)
            made = self.local(call, arg.param, "out")
            return f"{made}.data()" if out.kind == "array" else f"&{made}"
        if arg.kind == "callback":
            return self.local(call, arg.param, "cb")
        if arg.kind == "context":
            return self.local(call, arg.of, "ctx")
        if arg.kind == "value" and is_opaque_ptr(arg.typ, self.idioms.handles) in (
            self.classes
        ):
            return (
                f"({name} ? {name}->native_handle() : nullptr)"
                if arg.nullable
                else f"{name}.native_handle()"
            )
        if arg.kind == "value" and self.param_type(arg) != self.c(arg.typ):
            return f"&{name}"
        return name

    def results(self, call: Call):
        found = []
        count = "ret" if call.returns == "count" else None
        for out in call.outs:
            name = self.local(call, out.param, "out")  # the parameter may name a type
            if out.kind == "array":
                found.append((f"std::vector<{self.elem(out.typ)}>", name))
                count = None
            elif out.kind == "handle" and not call.errno:
                cls = self.name(out.typ.to.name)
                found.append(
                    (
                        f"std::optional<{cls}>",
                        f"{name} ? std::optional<{cls}>(std::in_place, {name})"
                        " : std::nullopt",
                    )
                )
            elif out.kind == "handle":
                found.append(
                    (
                        self.name(out.typ.to.name),
                        f"{self.name(out.typ.to.name)}({name})",
                    )
                )
            else:
                found.append((self.c(out.typ), name))
        if count:
            found.append(("std::size_t", "static_cast<std::size_t>(ret)"))

        ret = call.ret
        if call.returns == "value":
            found.append((self.c(ret), "ret"))
        elif call.returns == "string":
            if call.nullable:
                found.append(
                    (
                        "std::optional<std::string_view>",
                        "ret ? std::optional<std::string_view>(ret) : std::nullopt",
                    )
                )
            else:
                found.append(("std::string_view", "std::string_view(ret)"))
        elif (
            call.returns == "pointer"
            and isinstance(ret.to, (types.Record, types.Builtin))
            and not is_void_ptr(ret)
            and copyable(self.model, ret.to)
        ):
            typ = self.c(
                types.Pointer(to=ret.to.model_copy(update={"const": False})).to
            )
            if call.nullable:
                found.append(
                    (
                        f"std::optional<{typ}>",
                        f"ret ? std::optional<{typ}>(*ret) : std::nullopt",
                    )
                )
            else:
                found.append((typ, "*ret"))
        elif call.returns in ("pointer", "handle"):
            found.append((self.c(ret), "ret"))
        return found

    def signature(self, call: Call, owner: Optional[str] = None) -> tuple:
        """(template line, return type, name, params, const) of 'call'"""

        params, template = [], ""
        callbacks = [a for a in call.args if a.kind == "callback"]
        for arg in call.args:
            typ = self.param_type(arg)
            if arg.kind == "callback":
                typ = f"{self.tparam(call, arg)} &&"
            if typ is None or arg.kind == "self":
                continue
            name = self.pname(arg.param)
            if typ == self.c(arg.typ):
                params.append(self.c(arg.typ, name))
            else:
                params.append(f"{typ}{'' if typ.endswith(('&', '*')) else ' '}{name}")
        if callbacks:
            names = ", ".join(f"class {self.tparam(call, a)}" for a in callbacks)
            template = f"template <{names}>"
        results = self.results(call)
        if not results:
            rtype = "void"
        elif len(results) == 1:
            rtype = results[0][0]
        else:
            rtype = f"std::tuple<{', '.join(t for t, _ in results)}>"
        this = next((a for a in call.args if a.kind == "self"), None)
        const = bool(this and this.typ.to.const)
        return (
            template,
            rtype,
            self.fn_name(call) if owner is None else self.method_name(call),
            params,
            const,
        )

    def body(self, call: Call, null: bool = False) -> List[str]:
        """The statements of 'call'; with 'null', for no callback at all"""

        lines: List[str] = []
        for arg in call.args:
            if arg.kind not in ("length", "capacity"):
                continue
            count = (
                f"{self.pname(arg.of)}.size()"
                if arg.kind == "length"
                else f"static_cast<std::size_t>({self.pname(arg.param)})"
            )
            for other in arg.shared:
                if next(a for a in call.args if a.param == other).kind == "out":
                    continue
                lines += [
                    f"if ({self.pname(other)}.size() != {count}) {{",
                    f"\tthrow std::invalid_argument(\"'{other}' does not have the"
                    f" count '{arg.param}'\");",
                    "}",
                ]
        for arg in call.args:
            name = self.pname(arg.param)
            if arg.kind == "out":
                out = next(o for o in call.outs if o.param == arg.param)
                made = self.local(call, arg.param, "out")
                if out.kind == "array":
                    lines.append(
                        f"std::vector<{self.elem(out.typ)}> {made}"
                        f"({self.pname(out.capacity)});"
                    )
                elif out.kind == "handle":
                    lines.append(f"{self.c(out.typ)} {made} = nullptr;")
                else:
                    lines.append(f"{self.c(out.typ)} {made}{{}};")
            elif arg.kind == "callback" and not (null and arg.nullable):
                func = self.callback(arg.typ)
                params, passed, ctx = [], [], None
                for i, param in enumerate(func.params):
                    pname = f"a{i}"
                    params.append(self.c(param.typ, pname))
                    if is_void_ptr(param.typ):
                        ctx = pname
                    elif isinstance(param.typ, types.Pointer) and isinstance(
                        param.typ.to, types.Record
                    ):
                        passed.append(f"*{pname}")
                    else:
                        passed.append(pname)
                ret = self.c(func.ret)
                given = self.tparam(call, arg)
                if arg.lifetime in ("once", "handle"):
                    lines += self.held(call, arg, given, params, passed, ctx, ret)
                    continue
                fn_t, ref, tramp, cb, made = (
                    self.local(call, arg.param, s)
                    for s in ("fn", "ref", "tramp", "cb", "ctx")
                )
                call_expr = f"(*static_cast<{fn_t} *>({ctx}))({', '.join(passed)})"
                bare = f"std::remove_reference_t<{given}>"
                lines += [
                    f"std::conditional_t<std::is_function_v<{bare}>,"
                    f" std::decay_t<{given}>, {bare} &> {ref} = {name};",
                    f"using {fn_t} = std::remove_reference_t<decltype({ref})>;",
                    f"auto {tramp} = []({', '.join(params)}) noexcept -> {ret} {{",
                    f"\treturn {call_expr};" if ret != "void" else f"\t{call_expr};",
                    "};",
                    f"{self.c(arg.typ, cb)} = {tramp};",
                    f"void *{made} = const_cast<void *>(",
                    f"\tstatic_cast<const void *>(std::addressof({ref})));",
                ]
        args = ", ".join(self.param_expr(call, a, null) for a in call.args)
        results = self.results(call)
        uses_ret = call.errno or call.returns != "nothing"
        raw = f"::{call.function}({args});"
        lines.append(f"auto ret = {raw}" if uses_ret else raw)
        if call.errno:
            lines.append("if (ret < 0) {")
            for arg in call.args:
                if arg.kind != "callback" or (null and self.nulled(call, arg)):
                    continue
                if arg.lifetime == "once":
                    held_t = self.local(call, arg.param, "t")
                    ctx = self.local(call, arg.param, "ctx")
                    lines.append(f"\tdelete static_cast<{held_t} *>({ctx});")
                elif arg.lifetime == "handle":
                    lines.append("\tkeep_.pop_back();")
            lines += [
                "\tthrow std::system_error(static_cast<int>(-ret),"
                " std::generic_category(),",
                f'\t\t\t\t"{call.function}");',
                "}",
            ]
        for out in call.outs:
            if out.kind == "array":
                count = "ret" if call.returns == "count" else self.pname(out.capacity)
                made = self.local(call, out.param, "out")
                lines.append(f"{made}.resize(static_cast<std::size_t>({count}));")
        if len(results) == 1:
            lines.append(f"return {results[0][1]};")
        elif results:
            lines.append(f"return {{{', '.join(e for _, e in results)}}};")
        return lines

    def functions(self) -> set:
        """The names of the functions of the namespace"""

        return {
            self.fn_name(c)
            for c in self.idioms.calls
            if c.kind in ("function", "constructor") and self.usable(c)
        }

    def fn_name(self, call: Call) -> str:
        """The name of a function of the namespace, other than a C name the
        generated code uses and than the classes it defines; an alias of a
        record gives way to the function instead"""

        name = ident(call.name)
        enums = [e.name for e in self.model.entities if isinstance(e, decls.Enum)]
        typed = {self.name(n) for n in enums + list(self.classes)}
        taken = self.c_names - {call.function} | typed | RESERVED
        while name in taken:
            name += "_"
        return name

    def method_name(self, call: Call) -> str:
        """The name of a method, other than what its class has, the raw pointer
        native_handle() and the deleter, and than the handle classes"""

        name = ident(call.name)
        classes = {self.name(c) for c in self.classes}
        if name in {"native_handle", "deleter"} | classes:
            return f"{name}_"
        return name

    def held(
        self, call: Call, arg: Arg, given: str, params, passed, ctx, ret
    ) -> List[str]:
        """Statements moving the callable of a callback the library keeps to the
        heap: given once, the trampoline deletes it; else the handle keeps it"""

        name = self.pname(arg.param)
        held_t, tramp, cb, made, kept = (
            self.local(call, arg.param, s) for s in ("t", "tramp", "cb", "ctx", "held")
        )
        held = f"static_cast<{held_t} *>({ctx})"
        if arg.lifetime == "once":
            invoke = [f"\tstd::unique_ptr<{held_t}> f({held});"]
            call_expr = f"(*f)({', '.join(passed)})"
            store = [f"void *{made} = new {held_t}(std::forward<{given}>({name}));"]
        else:
            invoke = []
            call_expr = f"(*{held})({', '.join(passed)})"
            store = [
                f"auto {kept} =",
                f"\tstd::make_shared<{held_t}>(std::forward<{given}>({name}));",
                f"void *{made} = {kept}.get();",
                f"keep_.push_back({kept});",
            ]
        return (
            [
                f"using {held_t} = std::decay_t<{given}>;",
                f"auto {tramp} = []({', '.join(params)}) noexcept -> {ret} {{",
            ]
            + invoke
            + [
                f"\treturn {call_expr};" if ret != "void" else f"\t{call_expr};",
                "};",
                f"{self.c(arg.typ, cb)} = {tramp};",
            ]
            + store
        )

    def keeps(self, record: str) -> bool:
        """Whether the handle keeps callables, for its methods to give"""

        return any(
            a.kind == "callback" and a.lifetime == "handle"
            for call in self.idioms.of(record)["method"]
            for a in call.args
            if self.usable(call)
        )

    def usable(self, call: Call) -> bool:
        if (
            call.kind in ("method", "destructor", "constructor")
            and call.handle not in self.classes
        ):
            return False
        for arg in call.args:
            if arg.kind == "callback" and self.callback(arg.typ) is None:
                return False
        return True

    def nulled_signature(self, call: Call, params: List[str]) -> tuple:
        """(template, params) of the overload taking nullptr for every nullable
        callback"""

        nulled = {
            f"{self.tparam(call, a)} &&{self.pname(a.param)}"
            for a in call.args
            if a.kind == "callback" and a.nullable
        }
        kept = [
            f"class {self.tparam(call, a)}"
            for a in call.args
            if a.kind == "callback" and not a.nullable
        ]
        nparams = ["std::nullptr_t" if p in nulled else p for p in params]
        return (f"template <{', '.join(kept)}>" if kept else "", nparams)

    def definition(self, call: Call, owner: Optional[str] = None) -> List[str]:
        template, rtype, name, params, const = self.signature(call, owner)
        qual = f"{self.name(owner)}::" if owner else ""
        lines = [template] if template else []
        cv = " const" if const else ""
        lines.append(f"inline {rtype}\n{qual}{name}({', '.join(params)}){cv}")
        lines.append("{")
        lines += [f"\t{line}" for line in self.body(call)]
        lines.append("}")
        if any(a.kind == "callback" and a.nullable for a in call.args):
            # An overload for no callback, as nullptr is no callable for F
            ntemplate, nparams = self.nulled_signature(call, params)
            lines += (
                [""]
                + ([ntemplate] if ntemplate else [])
                + [
                    f"inline {rtype}\n{qual}{name}({', '.join(nparams)})"
                    + (" const" if const else ""),
                    "{",
                ]
            )
            lines += [f"\t{line}" for line in self.body(call, null=True)]
            lines.append("}")
        return lines

    def declaration(self, call: Call, owner: str) -> List[str]:
        template, rtype, name, params, const = self.signature(call, owner)
        lines = comment(self.idioms.decl(call.function).doc, "\t")
        if template:
            lines.append(f"\t{template}")
        lines.append(
            f"\t{rtype} {name}({', '.join(params)}){' const' if const else ''};"
        )
        if any(a.kind == "callback" and a.nullable for a in call.args):
            ntemplate, nparams = self.nulled_signature(call, params)
            if ntemplate:
                lines.append(f"\t{ntemplate}")
            lines.append(
                f"\t{rtype} {name}({', '.join(nparams)}){' const' if const else ''};"
            )
        return lines

    def handle_class(self, record: str) -> List[str]:
        calls = self.idioms.of(record)
        cls = self.name(record)
        raw = f"{cgen.tag(self.model.find(record, decls.RECORDS))} ::{record}"
        destructor = calls["destructor"][0] if calls["destructor"] else None
        lines = comment(self.model.find(record, decls.RECORDS).doc)
        lines += [
            f"class {cls} {{",
            "public:",
            f"\texplicit {cls}({raw} *ptr) noexcept : ptr_(ptr) {{}}",
            "",
            "\t/// The raw pointer, still owned by this",
            f"\t{raw} *native_handle() const noexcept {{ return ptr_.get(); }}",
        ]
        if self.keeps(record):
            # The handle is destroyed before its closures, which C may call
            # until then; they stay for good where it is not destroyed, or
            # destroying it fails
            leak: List[str] = []
            if not destructor or destructor.errno:
                test = (
                    f"ptr_ && ::{destructor.function}(ptr_.release()) < 0"
                    if destructor
                    else "ptr_"
                )
                leak = [
                    f"\t\tif ({test}) {{",
                    "\t\t\t(void)new decltype(keep_)(std::move(keep_));",
                    "\t\t}",
                ]
                lines += ["", f"\t~{cls}()", "\t{", *leak, "\t}"]
            lines += [
                "",
                f"\t{cls}({cls} &&) noexcept = default;",
                f"\t{cls} &operator=({cls} &&other) noexcept",
                "\t{",
                "\t\tif (this != &other) {",
                *("\t" + line for line in leak),
                "\t\t\tptr_ = std::move(other.ptr_);",
                "\t\t\tkeep_ = std::move(other.keep_);",
                "\t\t}",
                "\t\treturn *this;",
                "\t}",
            ]
        for call in calls["method"]:
            if self.usable(call):
                lines += [""] + self.declaration(call, record)
        if destructor:
            lines += [""] + comment(self.idioms.decl(destructor.function).doc, "\t")
            close_rtype = "void"
            lines.append(f"\t{close_rtype} {self.method_name(destructor)}();")
        lines += [
            "",
            "private:",
            "\tstruct deleter {",
            f"\t\tvoid operator()({raw} *ptr) const noexcept",
            "\t\t{",
            "\t\t\t"
            + (f"(void)::{destructor.function}(ptr);" if destructor else "(void)ptr;"),
            "\t\t}",
            "\t};",
        ]
        if self.keeps(record):
            lines.append("\tmutable std::vector<std::shared_ptr<void>> keep_;")
        lines += [
            f"\tstd::unique_ptr<{raw}, deleter> ptr_;",
            "};",
        ]
        return lines

    def destructor(self, record: str) -> List[str]:
        calls = self.idioms.of(record)
        if not calls["destructor"]:
            return []
        call = calls["destructor"][0]
        cls = self.name(record)
        lines = [f"inline void\n{cls}::{self.method_name(call)}()", "{"]
        if call.errno:
            lines += [
                "\tif (!ptr_) {",
                "\t\treturn;",
                "\t}",
                "\tauto ret = ::" + call.function + "(ptr_.release());",
                "\tif (ret < 0) {",
            ]
            if self.keeps(record):
                lines.append("\t\t(void)new decltype(keep_)(std::move(keep_));")
            lines += [
                "\t\tthrow std::system_error(static_cast<int>(-ret),"
                " std::generic_category(),",
                f'\t\t\t\t\t"{call.function}");',
                "\t}",
            ]
            if self.keeps(record):
                lines.append("\tkeep_.clear();")
        else:
            lines.append("\tptr_.reset();")
            if self.keeps(record):
                lines.append("\tkeep_.clear();")
        lines.append("}")
        return lines

    def enum(self, enum: decls.Enum) -> List[str]:
        name = self.name(enum.name)
        underlying = cgen.decl(enum.underlying) if enum.underlying else "int"
        member_prefix = enum.name.upper()
        lines = comment(enum.doc)
        lines.append(f"enum class {name} : {underlying} {{")
        named: Dict[int, Tuple[str, str]] = {}
        for member in enum.members:
            mname = ident(strip(member.name, member_prefix).lower())
            if mname[:1].isdigit():
                mname = ident(member.name.lower())
            lines.append(f"\t{mname} = ::{member.name},")
            named.setdefault(member.value, (mname, member.name))
        lines += ["};", ""]
        lines += [
            "/// The C name of the value, none when it is none of those named",
            "inline std::optional<std::string_view>",
            f"name({name} value)",
            "{",
            "\tswitch (value) {",
        ]
        for mname, cname in named.values():
            lines += [f"\tcase {name}::{mname}:", f'\t\treturn "{cname}";']
        lines += ["\tdefault:", "\t\treturn std::nullopt;", "\t}", "}"]
        return lines

    def printers(self) -> List[str]:
        """yaml() and json() of every record with fields, printing what the
        pretty-printers of the C API print, without calling them"""

        printer = Printer(self.model)
        records = cgen.ordered_records(self.model)
        lines = ["namespace detail {", ""] + HELPERS
        for record in records:
            raw = f"{cgen.tag(record)} ::{record.name}"
            lines += [
                "",
                f"inline void json(std::string &out, const {raw} &obj);",
                f"inline void yaml(std::string &out, const {raw} &obj, int indent);",
            ]
        for record in records:
            raw = f"{cgen.tag(record)} ::{record.name}"
            unused = "" if printer.named(record) else "[[maybe_unused]] "
            lines += [
                "",
                "inline void",
                f"json(std::string &out, {unused}const {raw} &obj)",
                "{",
                *["\t" + line for line in printer.json_body(record)],
                "}",
                "",
                "inline void",
                f"yaml({unused}std::string &out, {unused}const {raw} &obj,"
                f" {unused}int indent)",
                "{",
                *["\t" + line for line in printer.yaml_body(record)],
                "}",
            ]
        lines += ["", "} // namespace detail"]
        for record in records:
            raw = f"{cgen.tag(record)} ::{record.name}"
            lines += [
                "",
                f"/// The YAML of a {cgen.tag(record)} {record.name},"
                f" as {record.name}_pr() prints it",
                "inline std::string",
                f"yaml(const {raw} &obj)",
                "{",
                f'\tstd::string out = "{record.name}:\\n";',
                "\tdetail::yaml(out, obj, 2);",
                "\treturn out;",
                "}",
                "",
                f"/// The JSON of a {cgen.tag(record)} {record.name}, on one line,"
                f" as {record.name}_pr() prints it",
                "inline std::string",
                f"json(const {raw} &obj)",
                "{",
                "\tstd::string out;",
                "\tdetail::json(out, obj);",
                "\treturn out += '\\n';",
                "}",
            ]
        return lines

    def accessors(self, record) -> List[str]:
        """Functions reading and writing the parts of the fields of bits of
        'record', overloaded on it; the C records are C's, without methods"""

        records = [e.name for e in self.model.entities if isinstance(e, decls.RECORDS)]
        enums = [e.name for e in self.model.entities if isinstance(e, decls.Enum)]
        typed = {self.name(n) for n in records + enums + list(self.classes)}
        raw = f"{cgen.tag(record)} ::{record.name}"
        lines: List[str] = []
        for field in record.fields:
            typ = self.c(field.typ)
            for mask in field.masks:
                name = ident(f"{field.name}_{mask.name}")
                while name in typed | RESERVED:
                    name += "_"
                bits = f"{mask.width} bit{'s' * (mask.width > 1)}"
                lines += comment(mask.doc)
                lines += [
                    f"inline {typ}",
                    f"{name}(const {raw} &obj) noexcept",
                    "{",
                    f"\treturn static_cast<{typ}>((obj.{field.name} & {mask.value:#x}u)"
                    f" >> {mask.lo});",
                    "}",
                    "",
                    f"/// Set the part of '{field.name}' that {name}() reads;",
                    f"/// std::out_of_range when 'value' does not fit in {bits}",
                    "inline void",
                    f"set_{name}({raw} &obj, {typ} value)",
                    "{",
                    f"\tif (value > {mask.largest:#x}u) {{",
                    f'\t\tthrow std::out_of_range("{name} is {bits}");',
                    "\t}",
                    f"\tconst {typ} mask = {mask.value:#x}u;",
                    f"\tobj.{field.name} = static_cast<{typ}>((obj.{field.name}"
                    f" & static_cast<{typ}>(~mask)) | static_cast<{typ}>(value <<"
                    f" {mask.lo}));",
                    "}",
                    "",
                ]
        return lines

    def operators(self) -> List[str]:
        """operator<<, in the global namespace, where the records are, for ADL"""

        lines = []
        for record in cgen.ordered_records(self.model):
            lines += [
                "",
                "inline std::ostream &",
                "operator<<(std::ostream &os,"
                f" const {cgen.tag(record)} ::{record.name} &obj)",
                "{",
                f"\treturn os << {self.ns}::yaml(obj);",
                "}",
            ]
        return lines

    def render(self) -> str:
        out: List[str] = self.printers() + [""]
        for enum in [e for e in self.model.entities if isinstance(e, decls.Enum)]:
            out += self.enum(enum) + [""]
        for record in [e for e in self.model.entities if isinstance(e, decls.RECORDS)]:
            if record.name in self.idioms.handles:
                continue
            alias = self.name(record.name)
            if strip(record.name, self.prefix) == record.name:
                continue
            if alias not in self.functions():
                out.append(f"using {alias} = {cgen.tag(record)} ::{record.name};")
        out.append("")
        for record in cgen.ordered_records(self.model):
            out += self.accessors(record)
        out += [f"class {self.name(record)};" for record in self.classes]
        if self.classes:
            out.append("")
        for record in self.classes:
            out += self.handle_class(record) + [""]
        for record in self.classes:
            for call in self.idioms.of(record)["method"]:
                if self.usable(call):
                    out += self.definition(call, record) + [""]
            out += self.destructor(record) + [""]
        for call in self.idioms.calls:
            if call.kind == "constructor" and self.usable(call):
                out += comment(self.idioms.decl(call.function).doc)
                out += self.definition(call) + [""]
        for call in self.idioms.functions():
            if self.usable(call):
                out += comment(self.idioms.decl(call.function).doc)
                out += self.definition(call) + [""]
        return "\n".join(out).rstrip() + "\n"
