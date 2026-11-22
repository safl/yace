# SPDX-FileCopyrightText: Simon A. F. Lund <os@safl.dk>
#
# SPDX-License-Identifier: GPL-2.0-only

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
from functools import cached_property
from typing import Dict, List, Optional

from yace.ir import decls, types
from yace.ir.semantics import is_void_ptr
from yace.targets.idiom import (
    RELEASES,
    Arg,
    Call,
    Idioms,
    call_doc,
    copyable,
    is_opaque_ptr,
    local,
)
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


# The structs of the buffer pattern. They bind no name but those Locals renames,
# and fields, which it does not, as Zig forbids a local to shadow a declaration
BUFFER = """\
/// Memory the library allocated, freed by deinit() with what it was allocated
/// with, which must outlive it. The memory may be a device's, such as a GPU's,
/// which the CPU cannot read, and nothing in the API says which; slice() is for
/// memory of the host only.
pub const Buffer = struct {
    ptr: *anyopaque,
    len: usize,
    ctx: ?*anyopaque,
    free_fn: *const fn (?*anyopaque, *anyopaque) void,
    realloc_fn: ?*const fn (?*anyopaque, *anyopaque, usize) ?*anyopaque,

    /// The memory as bytes; for memory of the host only
    pub fn slice(self: Buffer) []u8 {
        return @as([*]u8, @ptrCast(self.ptr))[0..self.len];
    }

    /// Resize the memory to 's' bytes, keeping its bytes up to the smaller
    /// size; error.OutOfMemory where it cannot, leaving the memory unchanged
    pub fn realloc(self: *Buffer, s: usize) anyerror!void {
        const h = self.realloc_fn orelse return error.Unsupported;
        self.ptr = h(self.ctx, self.ptr, s) orelse return error.OutOfMemory;
        self.len = s;
    }

    /// Free the memory
    pub fn deinit(self: Buffer) void {
        self.free_fn(self.ctx, self.ptr);
    }
};"""

REGISTRATION = """\
/// Memory of the caller's that the library uses until unregister(). The
/// memory, and what it was registered with, must outlive it.
pub const Registration = struct {
    memory: []u8,
    ctx: ?*anyopaque,
    unregister_fn: *const fn (?*anyopaque, *anyopaque) anyerror!void,

    /// Unregister the memory
    pub fn unregister(self: Registration) anyerror!void {
        return self.unregister_fn(self.ctx, @ptrCast(self.memory.ptr));
    }

    /// As unregister(), without its error, for `defer registration.deinit()`
    pub fn deinit(self: Registration) void {
        self.unregister() catch {};
    }
};"""


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
        # same struct, as two C names that differ by a trailing '_' have the
        # same camelCase name
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
        """A parameter's name, unescaped and not taken by a declaration: a name
        that is taken, a capture or a primitive type gets '_arg' appended, then
        '_' until it is not taken. A name already ending in '_arg', or in '_arg'
        and '_', gets '_arg' appended too, so no two parameters share a name"""

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

    def partial_name(self, call: Call) -> str:
        """The parameter through which a partial call that fails returns what
        it wrote"""

        taken = {self.pname(a.param) for a in call.args}
        name = "partial"
        while name in taken:
            name += "_"
        return name

    def value(self, call: Call):
        """The type and expression of what 'call' returns when it succeeds"""

        results = self.results(call)
        if not results:
            return "void", None
        if len(results) == 1:
            return results[0]
        rtype = f"struct {{ {', '.join(t for t, _ in results)} }}"
        return rtype, f".{{ {', '.join(e for _, e in results)} }}"

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
            if self.makes(call) == "register" and arg.param == call.memory.ptr:
                found.append(f"{name}: []u8")
            elif self.makes(call) == "register" and arg.param == call.memory.nbytes:
                continue  # the length of the slice
            elif arg.kind == "self":
                found.append(f"self: {self.struct_name(call.handle)}")
            elif arg.kind == "string":
                opt = "?" if arg.nullable else ""
                string = "[]const u8" if call.counted(arg) else "[*:0]const u8"
                found.append(f"{name}: {opt}{string}")
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
        if self.makes(call) == "register" and arg.param == call.memory.ptr:
            return f"@ptrCast({name}.ptr)"
        if self.makes(call) == "register" and arg.param == call.memory.nbytes:
            return f"@intCast({self.pname(call.memory.ptr)}.len)"
        if arg.kind == "value" and self.given_handle(arg.typ):
            return f"if ({name}) |h| h.ptr else null" if arg.nullable else f"{name}.ptr"
        if arg.kind == "self":
            return "self.ptr"
        if arg.kind == "string" and call.counted(arg):
            return f"if ({name}) |s| s.ptr else null" if arg.nullable else f"{name}.ptr"
        if arg.kind == "sequence":
            ptr = "@ptrCast(s.ptr)" if is_void_ptr(arg.typ) else "s.ptr"
            if arg.nullable:
                return f"if ({name}) |s| {ptr} else null"
            return ptr.replace("s.", f"{name}.", 1)
        if arg.kind == "length":
            return f"@intCast({self.size(call, arg.of)})"
        if arg.kind == "capacity":
            return f"@intCast({self.pname(arg.of)}.len)"
        if arg.kind == "size":
            return f"@sizeOf({self.z(call.sized(arg))})"
        if arg.kind == "callback":
            return f"&{self.local(call, arg.param, 'trampoline')}.call"
        if arg.kind == "context":
            return f"@ptrCast(@constCast({self.local(call, arg.of, 'context')}))"
        if arg.kind == "count":
            return f"&{self.out_name(call, arg.param)}"
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
        if self.makes(call) == "register":
            return [(self.made_type(call), self.made(call))]
        found = []
        count = "ret" if call.returns == "count" else None
        for out in call.outs:
            name = self.pname(out.param)
            if out.kind == "array" and out.count:
                length = self.out_name(call, out.count)
                found.append(
                    (f"[]{self.elem(out.typ)}", f"{name}[0..@intCast({length})]")
                )
            elif out.kind == "array":
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
            elif types.is_string(out.typ):
                made = self.out_name(call, out.param)
                span = f"std.mem.span(@as([*:0]const u8, @ptrCast({made})))"
                found.append(("?[:0]const u8", f"if ({made} == null) null else {span}"))
            else:
                found.append((self.z(out.typ), self.out_name(call, out.param)))
        if count:
            found.append(("usize", "@intCast(ret)"))

        ret = call.ret
        if self.makes(call) == "alloc":
            found.append((self.made_type(call), self.made(call)))
        elif call.returns == "value":
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
        rtype, rexpr = self.value(call)
        value = rtype
        if call.errno or (self.makes(call) == "alloc" and not call.nullable):
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
            if arg.kind == "count":
                made = self.out_name(call, arg.param)
                body.append(f"var {made}: {self.z(arg.typ.to)} = 0;")
            elif arg.kind == "out":
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
        if call.partial:
            body += [
                "if (ret < 0) {",
                f"    if ({self.partial_name(call)}) |p| p.* = {rexpr};",
                "    return errnoError(@intCast(ret));",
                "}",
            ]
        elif call.errno:
            body.append("if (ret < 0) return errnoError(@intCast(ret));")
        body += self.releases(call)
        if rexpr is not None:
            body.append(f"return {rexpr};")

        shown, errors = call_doc(
            call,
            func.doc,
            self.pname,
            f"On failure, it writes to `{self.partial_name(call)}`, when given, what"
            " it returns when it succeeds, with what was written before it failed.",
            buffers=True,
        )
        if self.makes(call) == "register":
            params_doc = dict(shown.params)
            params_doc.pop(self.pname(call.memory.nbytes), None)
            shown = shown.model_copy(update={"params": params_doc})
        lines = [f"/// {line}".rstrip() for line in zgen.doc_lines(shown, errors)]
        lines += ["///", f"/// Calls `{call.function}`."]
        for arg in call.args:
            if arg.kind != "callback" or arg.lifetime == "call":
                continue
            until = (
                "it has been called, once"
                if arg.lifetime == "once"
                else "the handle is destroyed"
            )
            context = self.local(call, arg.param, "context")
            lines += ["///", f"/// `{context}` must live until {until}."]
        name = self.fn_name(call)
        params = self.params(call)
        if call.partial:
            params.append(f"{self.partial_name(call)}: ?*{value}")
        lines.append(f"pub fn {name}({', '.join(params)}) {rtype} {{")
        lines += [f"    {line}" for line in body]
        lines.append("}")
        return [f"{indent}{line}".rstrip() for line in lines]

    def context(self, call: Call, partner: Optional[Call]) -> Optional[str]:
        """The context a release function of 'partner' is given, from the
        arguments of 'call': the pointer of the one handle 'partner' takes
        besides the address and the size, or null where it takes none; None
        where it takes more, or what is not a handle of 'call'"""

        if partner is None or partner.memory is None:
            return None
        given = {a.param: a for a in call.args}
        found = []
        for param in self.idioms.decl(partner.function).params:
            if param.name in (partner.memory.ptr, partner.memory.nbytes):
                continue
            arg = given.get(param.name)
            if arg is not None and arg.kind == "self":
                found.append("self.ptr")
            elif arg is not None and arg.kind == "value" and not arg.nullable:
                if not self.given_handle(arg.typ):
                    return None
                found.append(f"{self.pname(arg.param)}.ptr")
            else:
                return None
        if len(found) > 1:
            return None
        return found[0] if found else "null"

    def makes(self, call: Call) -> Optional[str]:
        """'alloc' where 'call' returns a Buffer, 'register' where it returns a
        Registration: where the struct can release what 'call' made"""

        if call.memory is None or call.memory.role not in ("alloc", "register"):
            return None
        role = "free" if call.memory.role == "alloc" else "unregister"
        if self.context(call, self.idioms.partner(call, role)) is None:
            return None
        return call.memory.role

    def bound(self, call: Call) -> bool:
        """Whether 'call' is bound by a name of its own, not only through the
        struct of the buffer pattern that calls it"""

        if call.memory is None or call.memory.role not in RELEASES:
            return True
        owner = self.idioms.owner(call)
        return owner is None or not self.makes(owner)

    def release(self, call: Call, role: str, name: str) -> List[str]:
        """A struct 'name' whose function 'call' calls the partner of the role
        'role', given the context, the address and, to resize, the size"""

        partner = self.idioms.partner(call, role)
        if partner is None or self.context(call, partner) is None:
            return []
        args = []
        for param in self.idioms.decl(partner.function).params:
            if param.name == partner.memory.ptr:
                args.append("p")
            elif param.name == partner.memory.nbytes:
                args.append("@intCast(s)")
            else:
                args.append("@ptrCast(@alignCast(context))")
        raw = f"{zgen.ident(partner.function)}({', '.join(args)})"
        if role == "realloc":
            head = "fn call(context: ?*anyopaque, p: *anyopaque, s: usize) ?*anyopaque"
            body = [f"return {raw};"]
        elif role == "unregister":
            head = "fn call(context: ?*anyopaque, p: *anyopaque) anyerror!void"
            body = [f"_ = {raw};"] if partner.returns != "nothing" else [f"{raw};"]
            if partner.errno:
                body = [
                    f"const err = {raw};",
                    "if (err < 0) return errnoError(@intCast(err));",
                ]
        else:
            head = "fn call(context: ?*anyopaque, p: *anyopaque) void"
            unused = partner.errno or partner.returns != "nothing"
            body = [f"_ = {raw};" if unused else f"{raw};"]
        return (
            [f"const {name} = struct {{", f"    {head} {{"]
            + [f"        {line}" for line in body]
            + ["    }", "};"]
        )

    def releases(self, call: Call) -> List[str]:
        """The structs of the functions that release what 'call' made"""

        if self.makes(call) == "register":
            return self.release(call, "unregister", "a0")
        if self.makes(call) == "alloc":
            return self.release(call, "free", "a0") + self.release(
                call, "realloc", "a1"
            )
        return []

    def made_type(self, call: Call) -> str:
        if self.makes(call) == "register":
            return self.registration_struct
        return f"?{self.buffer_struct}" if call.nullable else self.buffer_struct

    def made(self, call: Call) -> str:
        """The expression of the Buffer or the Registration 'call' made"""

        if self.makes(call) == "register":
            ctx = self.context(call, self.idioms.partner(call, "unregister"))
            memory = self.pname(call.memory.ptr)
            return f".{{ .memory = {memory}, .ctx = {ctx}, .unregister_fn = &a0.call }}"
        ctx = self.context(call, self.idioms.partner(call, "free"))
        resize = "&a1.call" if self.release(call, "realloc", "a1") else "null"
        fields = (
            f" .len = @intCast({self.pname(str(call.memory.nbytes))}),"
            f" .ctx = {ctx}, .free_fn = &a0.call, .realloc_fn = {resize} }}"
        )
        cls = self.buffer_struct
        if call.nullable:
            return f"if (ret) |p| {cls}{{ .ptr = p,{fields} else null"
        return f"{cls}{{ .ptr = ret orelse return error.OutOfMemory,{fields}"

    def available(self, name: str) -> str:
        taken = self.declared | set(self.fn_names.values())
        taken |= {self.struct_name(h) for h in self.idioms.handles}
        while name in taken:
            name += "_"
        return name

    @cached_property
    def buffer_struct(self) -> str:
        return self.available("Buffer")

    @cached_property
    def registration_struct(self) -> str:
        return self.available("Registration")

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
            if self.usable(call) and self.bound(call):
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
            if self.usable(call) and self.bound(call):
                lines += [""] + self.function(call, "")
        made = {self.makes(c) for c in self.idioms.calls if self.usable(c)}
        if "alloc" in made:
            text = re.sub(r"\bBuffer\b", self.buffer_struct, BUFFER)
            lines += [""] + text.splitlines()
        if "register" in made:
            text = re.sub(r"\bRegistration\b", self.registration_struct, REGISTRATION)
            lines += [""] + text.splitlines()
        return self.locals.rename("\n".join(lines), "idiomatic")
