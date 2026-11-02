"""
The idiomatic Zig layer of the bindings, over the raw externs: handles as
structs with their methods and a ``deinit``, errors as Zig errors named for the
errno, what is written through ``[out]`` pointers returned, slices for arrays,
a caller's buffer for those written, ``[*:0]const u8`` and ``[:0]const u8`` for
strings, optionals where NULL is allowed, and a context pointer with a comptime
function for callbacks. See :py:mod:`yace.targets.idiom` for what is derived
from where. Names are camelCase for functions, without the prefix.
"""

import re
from typing import Dict, List, Optional

from yace.ir import decls, types
from yace.ir.semantics import is_void_ptr
from yace.targets.idiom import Arg, Call, Idioms, copyable, is_opaque_ptr, local
from yace.targets.python.pygen import camel

from . import zgen

INTERNAL = set(
    "self ret context w chars addr chr buf len fmt value obj flags indent err tag"
    " field o p h s ptr".split()
)


# The captures and locals of the idiomatic functions, and the function of a
# trampoline, which a parameter may not shadow either
CAPTURES = {"s", "h", "p", "context", "call"}

# A parameter's name as renamed, which no other parameter may keep
RENAMED = re.compile(r"_arg_*$")

# The primitive types, which no name may shadow
PRIMITIVE = re.compile(
    r"[iu]\d+|f(16|32|64|80|128)|[iu]size|c_(u?(char|short|int|long|longlong)"
    r"|longdouble)|any(opaque|error|frame)|bool|void|noreturn|type"
    r"|comptime_(int|float)"
)


class Renderer(object):
    def __init__(self, idioms: Idioms, namer: zgen.Namer):
        self.idioms = idioms
        self.namer = namer
        self.model = idioms.model
        enums = [e for e in self.model.entities if isinstance(e, decls.Enum)]
        self.declared = {"std", "yace_pp", "errnoError", "errnoOf"}
        self.declared |= {e.name for e in self.model.entities if hasattr(e, "name")}
        self.declared |= {m.name for e in enums for m in e.members}
        self.declared |= set(namer.names.values()) | set(namer.stubs.values())
        # The names of the functions, each other than those before it in the
        # same struct, as C names a trailing '_' may tell apart are one here
        self.fn_names: Dict[str, str] = {}
        handed: Dict[Optional[str], set] = {}
        for call in idioms.calls:
            scope = call.handle if call.kind != "function" else None
            name = zgen.lower_camel(call.name)
            while self.unusable(name) or name in handed.setdefault(scope, set()):
                name += "_"
            handed[scope].add(name)
            self.fn_names[call.function] = name
        # What the module declares, which Zig forbids any local to shadow
        module = self.declared | set(self.fn_names.values())
        module |= {self.struct_name(h) for h in idioms.handles}
        self.locals = zgen.Locals(module)
        # Zig forbids a parameter to shadow a declaration: these are taken
        self.taken = module | {"self", "ret", "deinit"} | self.locals.renamed()

    def base(self, name: str) -> str:
        """A parameter's name, one not taken by a declaration, unescaped: else
        with '_arg', and '_' until it is not taken; one already so ending gets
        it too, so no two parameters share a name"""

        captured = name in CAPTURES or name == "_" or re.fullmatch(r"a\d+", name)
        primitive = PRIMITIVE.fullmatch(name)
        if name in self.taken or captured or primitive or RENAMED.search(name):
            found = f"{name}_arg"
            while found in self.taken:
                found += "_"
            return found
        return name

    def pname(self, name: str) -> str:
        """A parameter's name, one not taken by a declaration"""

        return zgen.ident(self.base(name))

    def local(self, call: Call, param: str, suffix: str) -> str:
        """The name made for 'param', other than that of a parameter or of a
        declaration, which Zig does not let it shadow"""

        taken = {self.base(a.param) for a in call.args} | self.taken
        return zgen.ident(local(self.base(param), suffix, taken))

    def struct_name(self, handle: str) -> str:
        """The name of a handle's struct, other than that of any raw type"""

        name = camel(self.idioms.handle_name(handle))
        if name in self.namer.names.values() or name in self.namer.stubs.values():
            name += "Handle"
        return zgen.ident(name)

    def fn_name(self, call: Call) -> str:
        """The name of a function, other than the parameters and locals of the
        module's own functions, which Zig does not let shadow it, and than a
        primitive type, which it does not let shadow either"""

        return self.fn_names[call.function]

    def unusable(self, name: str) -> bool:
        """Whether a function may not be named 'name': as a parameter or local of
        the module's own functions, a declaration, or a primitive type"""

        internal = name in INTERNAL or re.fullmatch(r"(a|idx|item)\d+", name)
        return bool(internal or name in self.declared or PRIMITIVE.fullmatch(name))

    def out_name(self, call: Call, param: str) -> str:
        return self.local(call, param, "out")

    def z(self, typ, param=False) -> str:
        return self.namer.ztype(typ, param)

    def callback_type(self, typ) -> Optional[types.FunctionType]:
        typ = self.namer.resolve(typ)
        if isinstance(typ, types.Pointer) and isinstance(typ.to, types.FunctionType):
            return typ.to
        return None

    def is_ref(self, typ) -> bool:
        """Whether a pointer is given as a Zig pointer to one value"""

        return (
            isinstance(typ, types.Pointer)
            and not is_void_ptr(typ)
            and isinstance(typ.to, (types.Record, types.Builtin))
            and not self.namer.is_opaque(typ.to)
        )

    def params(self, call: Call) -> List[str]:
        found = []
        for arg in call.args:
            name = self.pname(arg.param)
            typ = arg.typ
            if arg.kind == "self":
                found.append(f"self: {self.struct_name(call.handle)}")
            elif arg.kind == "string":
                opt = "?" if arg.nullable else ""
                found.append(f"{name}: {opt}[*:0]const u8")
            elif arg.kind == "sequence":
                const = "const " if getattr(typ.to, "const", False) else ""
                opt = "?" if arg.nullable else ""
                found.append(f"{name}: {opt}[]{const}{self.elem(typ.to)}")
            elif arg.kind == "callback":
                func = self.callback_type(typ)
                passed = [
                    self.callback_param(p.typ)
                    for p in func.params
                    if not is_void_ptr(p.typ)
                ]
                context = self.local(call, arg.param, "context")
                found.append(f"{context}: anytype")
                found.append(
                    f"comptime {name}: fn (@TypeOf({context})"
                    + "".join(f", {p}" for p in passed)
                    + f") {self.z(func.ret)}"
                )
            elif arg.kind == "out":
                out = next(o for o in call.outs if o.param == arg.param)
                if out.kind == "array":
                    found.append(f"{name}: []{self.elem(out.typ)}")
            elif arg.kind == "value" and self.given_handle(typ):
                opt = "?" if arg.nullable else ""
                found.append(f"{name}: {opt}{self.struct_name(self.given_handle(typ))}")
            elif arg.kind == "value":
                if self.is_ref(typ):
                    const = "const " if typ.to.const else ""
                    opt = "?" if arg.nullable else ""
                    found.append(f"{name}: {opt}*{const}{self.z(typ.to)}")
                else:
                    found.append(f"{name}: {self.z(typ, True)}")
        return found

    def size(self, call: Call, param: str) -> str:
        """The number of elements of the slice given as 'param'"""

        arg = next(a for a in call.args if a.param == param)
        name = self.pname(param)
        return f"(if ({name}) |s| s.len else 0)" if arg.nullable else f"{name}.len"

    def callback_param(self, typ) -> str:
        if types.is_string(typ):
            return "[*:0]const u8"
        if self.is_ref(typ):
            const = "const " if typ.to.const else ""
            return f"*{const}{self.z(typ.to)}"
        return self.z(typ, True)

    def elem(self, typ) -> str:
        """The Zig type of an element of an array, a byte for void"""

        if isinstance(typ, types.Builtin) and typ.name == "void":
            return "u8"
        return self.z(typ)

    def given_handle(self, typ) -> Optional[str]:
        """The handle a parameter takes, other than the one a method is of"""

        handle = is_opaque_ptr(typ, self.idioms.handles)
        return handle if handle and any(self.idioms.of(handle).values()) else None

    def expr(self, call: Call, arg: Arg) -> str:
        name = self.pname(arg.param)
        if arg.kind == "value" and self.given_handle(arg.typ):
            return f"if ({name}) |h| h.ptr else null" if arg.nullable else f"{name}.ptr"
        if arg.kind == "self":
            return "self.ptr"
        if arg.kind == "sequence":
            ptr = "@ptrCast(s.ptr)" if is_void_ptr(arg.typ) else "s.ptr"
            if arg.nullable:
                return f"if ({name}) |s| {ptr} else null"
            return ptr.replace("s.", f"{name}.", 1)
        if arg.kind == "length":
            return f"@intCast({self.size(call, arg.of)})"
        if arg.kind == "capacity":
            return f"@intCast({self.pname(arg.of)}.len)"
        if arg.kind == "callback":
            return f"&{self.local(call, arg.param, 'trampoline')}.call"
        if arg.kind == "context":
            return f"@ptrCast(@constCast({self.local(call, arg.of, 'context')}))"
        if arg.kind == "out":
            out = next(o for o in call.outs if o.param == arg.param)
            return (
                f"@ptrCast({name}.ptr)"
                if out.kind == "array"
                else f"&{self.out_name(call, arg.param)}"
            )
        return name

    def trampoline(self, call: Call, arg: Arg) -> List[str]:
        name = self.pname(arg.param)
        func = self.callback_type(arg.typ)
        params, passed, ctx = [], [], None
        for i, param in enumerate(func.params):
            params.append(f"a{i}: {self.z(param.typ, True)}")
            if is_void_ptr(param.typ):
                ctx = f"a{i}"
            elif self.is_ref(param.typ):
                passed.append(f"a{i}")  # a C pointer coerces, checked for NULL
            else:
                passed.append(f"a{i}")
        context = self.local(call, arg.param, "context")
        return [
            f"const {self.local(call, arg.param, 'trampoline')} = struct {{",
            f"    fn call({', '.join(params)}) callconv(.c) {self.z(func.ret)} {{",
            f"        const context: @TypeOf({context}) = @ptrCast(@alignCast({ctx}));",
            f"        return {name}({', '.join(['context'] + passed)});",
            "    }",
            "};",
        ]

    def results(self, call: Call):
        found = []
        count = "ret" if call.returns == "count" else None
        for out in call.outs:
            name = self.pname(out.param)
            if out.kind == "array":
                found.append(
                    (
                        f"[]{self.elem(out.typ)}",
                        f"{name}[0..@intCast(ret)]" if count else name,
                    )
                )
                count = None
            elif out.kind == "handle" and not call.errno:
                struct = self.struct_name(out.typ.to.name)
                out_ptr = self.out_name(call, out.param)
                found.append(
                    (
                        f"?{struct}",
                        f"if ({out_ptr}) |p| {struct}{{ .ptr = p }} else null",
                    )
                )
            elif out.kind == "handle":
                struct = self.struct_name(out.typ.to.name)
                found.append(
                    (
                        struct,
                        f"{struct}{{ .ptr = {self.out_name(call, out.param)}"
                        " orelse return error.Unexpected }",
                    )
                )
            else:
                found.append((self.z(out.typ), self.out_name(call, out.param)))
        if count:
            found.append(("usize", "@intCast(ret)"))

        ret = call.ret
        if call.returns == "value":
            found.append((self.z(ret), "ret"))
        elif call.returns == "string":
            span = "std.mem.span(@as([*:0]const u8, @ptrCast(ret)))"
            if call.nullable:
                found.append(("?[:0]const u8", f"if (ret == null) null else {span}"))
            else:
                found.append(("[:0]const u8", span))
        elif (
            call.returns == "pointer"
            and self.is_ref(ret)
            and copyable(self.model, ret.to)
        ):
            typ = self.z(ret.to)
            if call.nullable:
                found.append((f"?{typ}", "if (ret == null) null else ret.*"))
            else:
                found.append((typ, "ret.*"))
        elif call.returns in ("pointer", "handle"):
            found.append((self.z(ret), "ret"))
        return found

    def function(self, call: Call, indent: str) -> List[str]:
        func = self.idioms.decl(call.function)
        results = self.results(call)
        if not results:
            rtype, rexpr = "void", None
        elif len(results) == 1:
            rtype, rexpr = results[0]
        else:
            rtype = f"struct {{ {', '.join(t for t, _ in results)} }}"
            rexpr = f".{{ {', '.join(e for _, e in results)} }}"
        if call.errno:
            rtype = f"anyerror!{rtype}"

        body: List[str] = []
        for arg in call.args:
            if arg.kind in ("length", "capacity"):
                for other in arg.shared:
                    body.append(
                        f"if ({self.size(call, other)} != {self.size(call, arg.of)})"
                        f" @panic(\"'{other}' does not have the count '{arg.param}'\");"
                    )
        for arg in call.args:
            if arg.kind == "out":
                out = next(o for o in call.outs if o.param == arg.param)
                made = self.out_name(call, arg.param)
                if out.kind == "handle":
                    body.append(f"var {made}: {self.z(out.typ)} = null;")
                elif out.kind != "array":
                    body.append(
                        f"var {made}: {self.z(out.typ)} ="
                        f" std.mem.zeroes({self.z(out.typ)});"
                    )
            elif arg.kind == "callback":
                body += self.trampoline(call, arg)
        args = ", ".join(self.expr(call, a) for a in call.args)
        uses_ret = call.errno or call.returns != "nothing"
        raw = f"{zgen.ident(call.function)}({args})"
        body.append(f"const ret = {raw};" if uses_ret else f"{raw};")
        if call.errno:
            body.append("if (ret < 0) return errnoError(@intCast(ret));")
        if rexpr is not None:
            body.append(f"return {rexpr};")

        lines = [f"/// {line}".rstrip() for line in zgen.doc_lines(func.doc)]
        lines += ["///", f"/// Calls `{call.function}`."]
        name = self.fn_name(call)
        lines.append(f"pub fn {name}({', '.join(self.params(call))}) {rtype} {{")
        lines += [f"    {line}" for line in body]
        lines.append("}")
        return [f"{indent}{line}".rstrip() for line in lines]

    def usable(self, call: Call) -> bool:
        for out in call.outs:
            if out.kind == "record":
                record = self.model.find(out.typ.name, decls.RECORDS)
                if record is None or not record.fields:
                    return False
        return True

    def handle(self, record: str) -> List[str]:
        calls = self.idioms.of(record)
        struct = self.struct_name(record)
        entity = self.model.find(record, decls.RECORDS)
        destructor = calls["destructor"][0] if calls["destructor"] else None
        lines = [f"/// {line}".rstrip() for line in zgen.doc_lines(entity.doc)]
        lines += [
            f"pub const {struct} = struct {{",
            f"    ptr: *{self.namer(record)},",
        ]
        for call in calls["constructor"] + calls["method"]:
            if self.usable(call):
                lines += [""] + self.function(call, "    ")
        if destructor:
            lines += [""] + self.function(destructor, "    ")
            name = self.fn_name(destructor)
            methods = {self.fn_name(c) for c in calls["method"] if self.usable(c)}
            if name != "deinit" and "deinit" not in methods:
                lines += [
                    "",
                    f"    /// As {name}(), for `defer handle.deinit()`",
                    f"    pub const deinit = {name};",
                ]
        lines.append("};")
        return lines

    def render(self) -> str:
        lines = [
            "/// The error of a negative errno: the Zig error of the same name",
            "pub fn errnoError(ret: c_int) anyerror {",
            "    return switch (@as(std.posix.E, @enumFromInt(-ret))) {",
            "        inline else => |tag| @field(anyerror, @tagName(tag)),",
            "        _ => error.Unexpected,",
            "    };",
            "}",
            "",
            "/// The errno of an error of errnoError(), 0 for any other",
            "pub fn errnoOf(err: anyerror) c_int {",
            '    inline for (@typeInfo(std.posix.E).@"enum".fields) |field| {',
            "        if (err == @field(anyerror, field.name))",
            "            return @intCast(field.value);",
            "    }",
            "    return 0;",
            "}",
        ]
        for record in self.idioms.handles:
            if any(self.idioms.of(record).values()):
                lines += [""] + self.handle(record)
        for call in self.idioms.functions():
            if self.usable(call):
                lines += [""] + self.function(call, "")
        return self.locals.rename("\n".join(lines), "idiomatic")
