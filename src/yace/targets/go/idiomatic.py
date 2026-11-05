"""
The idiomatic Go layer of the package, over the C functions: handles as
structs with their methods, errors as the last of the values returned, a
``syscall.Errno``, what is written through ``[out]`` pointers returned, slices
for arrays, a caller's slice for those written, strings for ``const char *``,
nil where NULL is allowed, and Go functions for callbacks. See
:py:mod:`yace.targets.idiom` for what is derived from where. Names are
CamelCase, exported, without the prefix.

A closure given to C is kept in a ``runtime/cgo.Handle``, held in C memory, as
cgo forbids C to keep a Go pointer: its value is what the C trampoline of the
callback gives back to the Go function it exports. It is released as the
callback's ``@lifetime`` says: when the call returns, once it has been called,
or when the handle is destroyed.
"""

from typing import Dict, List, Optional, Tuple

from yace.ir import decls, types
from yace.ir.semantics import is_void_ptr
from yace.targets.capi import cgen
from yace.targets.idiom import Call, Idioms, copyable, is_opaque_ptr, local
from yace.targets.python.pygen import camel

from . import ggen
from .ggen import Namer, Registry, doc_lines
from .raw import Raw, doc, param_names

# What the idiomatic functions bind besides their parameters; a method also
# binds its receiver, 'h'
LOCALS = {"ret", "ret_val"}

HELPERS = """
// yaceErrno is the error of the negative errno a C function returned
func yaceErrno(function string, ret int64) error {
	return fmt.Errorf("%s: %w", function, syscall.Errno(-ret))
}
""".strip(
    "\n"
)

CLOSURES = """
// yaceClosure is a Go function given to C, and whether C calls it once
type yaceClosure struct {
	fn   any
	once bool
}

// yaceKeep is C memory holding a handle of fn, as C may not hold a Go pointer,
// for C to give to the trampoline of the callback
func yaceKeep(fn any, once bool) unsafe.Pointer {
	ctx := C.malloc(C.size_t(unsafe.Sizeof(C.uintptr_t(0))))
	*(*C.uintptr_t)(ctx) = C.uintptr_t(cgo.NewHandle(yaceClosure{fn, once}))
	return ctx
}

// yaceRelease releases what yaceKeep made; nil is none
func yaceRelease(ctx unsafe.Pointer) {
	if ctx != nil {
		cgo.Handle(*(*C.uintptr_t)(ctx)).Delete()
		C.free(ctx)
	}
}

// yaceCalled is the function of ctx, released when it is called once
func yaceCalled(ctx unsafe.Pointer) any {
	closure := cgo.Handle(*(*C.uintptr_t)(ctx)).Value().(yaceClosure)
	if closure.once {
		yaceRelease(ctx)
	}
	return closure.fn
}
""".strip(
    "\n"
)


class Renderer(object):
    def __init__(self, idioms: Idioms, namer: Namer, raw: Raw):
        self.idioms = idioms
        self.namer = namer
        self.raw = raw
        self.model = idioms.model
        registry = namer.registry

        self.handles = [h for h in idioms.handles if any(idioms.of(h).values())]
        self.structs: Dict[str, str] = {}
        for handle in self.handles:
            name = camel(idioms.handle_name(handle)) or ggen.export(handle)
            if name in registry.taken:
                name += "Handle"
            self.structs[handle] = registry.add(name)

        # The callback typedefs given as closures, by C name
        self.callbacks: Dict[str, str] = {}
        for call in idioms.calls:
            for arg in call.args:
                if arg.kind == "callback" and self.usable(call) is None:
                    cname = arg.typ.name
                    if cname not in self.callbacks:
                        go = namer.type_name(arg.typ)
                        self.callbacks[cname] = registry.add(f"{go}Func")

        self.fn_names: Dict[str, str] = {}
        scopes: Dict[Optional[str], Registry] = {None: registry}
        for call in idioms.calls:
            scope = call.handle if call.kind in ("method", "destructor") else None
            if scope not in scopes:
                scopes[scope] = Registry({"Ptr"})
            name = camel(call.name) or ggen.export(call.function)
            self.fn_names[call.function] = scopes[scope].add(name)

    # Types

    def callback_type(self, typ) -> types.FunctionType:
        return self.namer.resolve(typ).to

    def closure_param(self, typ) -> str:
        """The Go type of a parameter of a closure, as C gives it"""

        if types.is_string(typ):
            return "string"
        return self.namer.gotype(typ, True)

    def closure_type(self, cname: str) -> str:
        func = self.callback_type(types.TypedefRef(name=cname))
        params = [
            f"{n} {self.closure_param(p.typ)}"
            for n, p in zip(
                param_names([p.name for p in func.params], self.reserved()),
                func.params,
            )
            if not is_void_ptr(p.typ)
        ]
        ret = self.namer.gotype(func.ret)
        return f"func({', '.join(params)}){' ' + ret if ret else ''}"

    def elem(self, typ) -> str:
        """The Go type of an element of a slice, a byte for void"""

        if isinstance(typ, types.Builtin) and typ.name == "void":
            return "byte"
        return self.namer.gotype(typ)

    def given_handle(self, typ) -> Optional[str]:
        """The handle a parameter takes, other than the one a method is of"""

        handle = is_opaque_ptr(typ, self.idioms.handles)
        return handle if handle in self.structs else None

    # Names

    def reserved(self, call: Optional[Call] = None) -> set:
        """What a parameter of 'call' must not be named"""

        method = call is not None and call.kind in ("method", "destructor")
        return self.raw.reserved() | LOCALS | ({"h"} if method else set())

    def pnames(self, call: Call) -> Dict[str, str]:
        """The Go names of the parameters of 'call', by their C names"""

        names = param_names([a.param for a in call.args], self.reserved(call))
        return {a.param: n for a, n in zip(call.args, names)}

    def local(self, call: Call, param: str, suffix: str) -> str:
        names = self.pnames(call)
        taken = set(names.values()) | self.reserved(call)
        return local(names[param], suffix, taken)

    # Calls

    def usable(self, call: Call) -> Optional[str]:
        """Why 'call' has no idiomatic form, if it has none"""

        func = self.idioms.decl(call.function)
        reason = self.raw.unbindable(func)
        if reason:
            return f"{call.function}() {reason}"
        for out in call.outs:
            if out.kind == "record":
                record = self.model.find(out.typ.name, decls.RECORDS)
                if record is None or not record.fields:
                    return f"what {call.function}() writes has no fields to return"
        for arg in call.args:
            if arg.kind != "callback":
                continue
            fn = self.callback_type(arg.typ)
            for typ in [fn.ret] + [p.typ for p in fn.params]:
                if self.namer.kind(typ) == "record":
                    return (
                        f"its callback '{arg.param}' takes or returns a record"
                        " by value"
                    )
        return None

    def params(self, call: Call) -> List[str]:
        names = self.pnames(call)
        found = []
        for arg in call.args:
            name = names[arg.param]
            typ = arg.typ
            if arg.kind == "string":
                found.append(f"{name} {'*' if arg.nullable else ''}string")
            elif arg.kind == "sequence":
                found.append(f"{name} []{self.elem(typ.to)}")
            elif arg.kind == "callback":
                found.append(f"{name} {self.callbacks[typ.name]}")
            elif arg.kind == "out":
                out = next(o for o in call.outs if o.param == arg.param)
                if out.kind == "array":
                    found.append(f"{name} []{self.elem(out.typ)}")
            elif arg.kind == "value":
                handle = self.given_handle(typ)
                given = f"*{self.structs[handle]}" if handle else None
                found.append(f"{name} {given or self.namer.gotype(typ, True)}")
        return found

    def size(self, call: Call, param: str) -> str:
        """The count of the slice or string given as 'param': of a string that
        may be nil, a local, 0 when it is nil"""

        arg = next(a for a in call.args if a.param == param)
        if arg.kind == "string" and arg.nullable:
            return self.local(call, param, "n")
        return f"len({self.pnames(call)[param]})"

    def slice_ptr(self, typ, name: str) -> str:
        """The pointer to the elements of the slice 'name', as cgo takes 'typ'"""

        data = f"unsafe.SliceData({name})"
        if is_void_ptr(typ):
            return f"unsafe.Pointer({data})"
        return self.namer.to_c(typ, data)

    def results(self, call: Call) -> List[Tuple[str, str, str]]:
        """The (type, expression, zero value) of each value 'call' returns,
        before the error"""

        names = self.pnames(call)
        namer = self.namer
        found = []
        count = call.returns == "count"
        for out in call.outs:
            name = names[out.param]
            if out.kind == "array":
                found.append(
                    (
                        f"[]{self.elem(out.typ)}",
                        f"{name}[:ret]" if count else name,
                        "nil",
                    )
                )
                count = False
            elif out.kind == "handle":
                struct = self.structs.get(out.typ.to.name)
                made = self.local(call, out.param, "out")
                if struct is None:
                    found.append((namer.gotype(out.typ), made, "nil"))
                else:
                    found.append(
                        (f"*{struct}", self.local(call, out.param, "made"), "nil")
                    )
            else:
                typ = namer.gotype(out.typ)
                found.append(
                    (typ, self.local(call, out.param, "out"), self.zero(out.typ))
                )
        if count:
            found.append(("int", "int(ret)", "0"))

        ret = call.ret
        if call.returns == "value":
            found.append((namer.gotype(ret), namer.from_c(ret, "ret"), self.zero(ret)))
        elif call.returns == "string":
            found.append(("string", "C.GoString(ret)", '""'))
            if call.nullable:
                found.append(("bool", "ret != nil", "false"))
        elif call.returns == "pointer" and self.is_copy(ret):
            typ = namer.gotype(ret.to)
            if call.nullable:
                found.append((typ, "ret_val", self.zero(ret.to)))
                found.append(("bool", "ret != nil", "false"))
            else:
                found.append(
                    (typ, f"*(*{typ})(unsafe.Pointer(ret))", self.zero(ret.to))
                )
        elif call.returns in ("pointer", "handle"):
            found.append((namer.gotype(ret), namer.from_c(ret, "ret"), "nil"))
        return found

    def is_copy(self, typ) -> bool:
        """Whether a returned pointer is to a value returned as a copy of it"""

        return (
            isinstance(typ, types.Pointer)
            and not is_void_ptr(typ)
            and isinstance(typ.to, (types.Record, types.Builtin))
            and not self.namer.is_opaque(typ.to)
            and copyable(self.model, typ.to)
        )

    def zero(self, typ) -> str:
        kind = self.namer.kind(typ)
        gotype = self.namer.gotype(typ)
        if kind == "record" or gotype.startswith("["):
            return f"{gotype}{{}}"
        if kind == "pointer":
            return "nil"
        if gotype == "bool":
            return "false"
        return "0"

    def function(self, call: Call, indent: str = "") -> List[str]:
        func = self.idioms.decl(call.function)
        name = self.fn_names[call.function]
        names = self.pnames(call)
        namer = self.namer
        method = call.kind in ("method", "destructor")

        body: List[str] = []
        args: List[str] = []
        after_err: List[str] = []  # what an error releases
        after_ok: List[str] = []  # what success keeps or releases

        counted = {
            p
            for a in call.args
            if a.kind in ("length", "capacity")
            for p in [str(a.of), *a.shared]
        }
        for arg in call.args:
            # A string that may be nil is counted when it is not
            if arg.kind == "string" and arg.nullable and arg.param in counted:
                count = self.size(call, arg.param)
                body += [
                    f"var {count} int",
                    f"if {names[arg.param]} != nil {{",
                    f"\t{count} = len(*{names[arg.param]})",
                    "}",
                ]
        for arg in call.args:
            if arg.kind not in ("length", "capacity"):
                continue
            for other in arg.shared:
                body += [
                    f"if {self.size(call, other)} != {self.size(call, str(arg.of))} {{",
                    f"\tpanic(\"{call.function}: '{other}' does not have the count"
                    f" '{arg.param}'\")",
                    "}",
                ]

        for arg in call.args:
            pname = names.get(arg.param, arg.param)
            typ = arg.typ
            if arg.kind == "self":
                args.append(namer.to_c(typ, "h.ptr"))
            elif arg.kind == "string":
                made = self.local(call, arg.param, "c")
                if arg.nullable:
                    body += [
                        f"var {made} *C.char",
                        f"if {pname} != nil {{",
                        f"\t{made} = C.CString(*{pname})",
                        f"\tdefer C.free(unsafe.Pointer({made}))",
                        "}",
                    ]
                else:
                    body += [
                        f"{made} := C.CString({pname})",
                        f"defer C.free(unsafe.Pointer({made}))",
                    ]
                args.append(made)
            elif arg.kind == "sequence":
                args.append(self.slice_ptr(typ, pname))
            elif arg.kind in ("length", "capacity"):
                args.append(namer.to_c(typ, self.size(call, str(arg.of))))
            elif arg.kind == "callback":
                fn = self.local(call, arg.param, "fn")
                ctx = self.local(call, arg.param, "ctx")
                ctype = namer.ctype(typ)
                trampoline = f"C.yace_{typ.name}"
                once = "true" if arg.lifetime == "once" else "false"
                keep = f"yaceKeep({pname}, {once})"
                if arg.nullable:
                    body += [
                        f"var {fn} {ctype}",
                        f"var {ctx} unsafe.Pointer",
                        f"if {pname} != nil {{",
                        f"\t{fn} = {ctype}({trampoline})",
                        f"\t{ctx} = {keep}",
                    ]
                    if arg.lifetime == "call":
                        body.append(f"\tdefer yaceRelease({ctx})")
                    body.append("}")
                    args.append(fn)
                else:
                    body.append(f"{ctx} := {keep}")
                    if arg.lifetime == "call":
                        body.append(f"defer yaceRelease({ctx})")
                    args.append(f"{ctype}({trampoline})")
                if arg.lifetime in ("once", "handle"):
                    after_err.append(f"yaceRelease({ctx})")
                if arg.lifetime == "handle":
                    after_ok.append(f"h.keep = append(h.keep, {ctx})")
            elif arg.kind == "context":
                args.append(self.local(call, arg.of, "ctx"))
            elif arg.kind == "out":
                out = next(o for o in call.outs if o.param == arg.param)
                if out.kind == "array":
                    args.append(self.slice_ptr(typ, pname))
                    continue
                made = self.local(call, arg.param, "out")
                body.append(f"var {made} {namer.gotype(typ.to)}")
                args.append(namer.to_c(typ, f"&{made}"))
            elif arg.kind == "value" and self.given_handle(typ):
                if arg.nullable:
                    made = self.local(call, arg.param, "ptr")
                    raw = namer.gotype(typ, True)
                    body += [
                        f"var {made} {raw}",
                        f"if {pname} != nil {{",
                        f"\t{made} = {pname}.ptr",
                        "}",
                    ]
                    args.append(namer.to_c(typ, made))
                else:
                    args.append(namer.to_c(typ, f"{pname}.ptr"))
            else:
                args.append(namer.to_c(typ, pname))

        results = self.results(call)
        rtypes = [t for t, _, _ in results] + (["error"] if call.errno else [])
        raw_call = f"C.{call.function}({', '.join(args)})"
        uses_ret = call.errno or call.returns != "nothing"
        body.append(f"ret := {raw_call}" if uses_ret else raw_call)
        zeros = [z for _, _, z in results]
        if call.errno:
            failed = f'yaceErrno("{call.function}", int64(ret))'
            body += ["if ret < 0 {"]
            body += [f"\t{line}" for line in after_err]
            body += [f"\treturn {', '.join(zeros + [failed])}", "}"]
        body += after_ok
        for out in call.outs:
            struct = self.structs.get(out.typ.to.name) if out.kind == "handle" else None
            if struct is None:
                continue
            made = self.local(call, out.param, "made")
            ptr = self.local(call, out.param, "out")
            if call.errno:
                failed = f'errors.New("{call.function}() gave no handle")'
                body += [
                    f"if {ptr} == nil {{",
                    f"\treturn {', '.join(zeros + [failed])}",
                    "}",
                    f"{made} := &{struct}{{ptr: {ptr}}}",
                ]
            else:
                body += [
                    f"var {made} *{struct}",
                    f"if {ptr} != nil {{",
                    f"\t{made} = &{struct}{{ptr: {ptr}}}",
                    "}",
                ]
        if call.returns == "pointer" and self.is_copy(call.ret) and call.nullable:
            copied = namer.gotype(call.ret.to)
            body += [
                f"var ret_val {copied}",
                "if ret != nil {",
                f"\tret_val = *(*{copied})(unsafe.Pointer(ret))",
                "}",
            ]
        if call.kind == "destructor":
            if self.keeps(call.handle):
                body += [
                    "for _, ctx := range h.keep {",
                    "\tyaceRelease(ctx)",
                    "}",
                    "h.keep = nil",
                ]
            body.append("h.ptr = nil")
        rexprs = [e for _, e, _ in results] + (["nil"] if call.errno else [])
        if rexprs:
            body.append(f"return {', '.join(rexprs)}")

        lines = doc(doc_lines(func.doc), f"{name} calls {call.function}.")
        for arg in call.args:
            if arg.kind == "callback" and arg.lifetime != "call":
                until = (
                    "it has been called, once"
                    if arg.lifetime == "once"
                    else "the handle is destroyed"
                )
                lines += ["//", f"// C keeps '{names[arg.param]}' until {until}."]
        if len(rtypes) > 1:
            rtype = f" ({', '.join(rtypes)})"
        else:
            rtype = f" {rtypes[0]}" if rtypes else ""
        receiver = f"(h *{self.structs[str(call.handle)]}) " if method else ""
        lines.append(f"func {receiver}{name}({', '.join(self.params(call))}){rtype} {{")
        lines += [f"\t{line}" for line in body]
        lines.append("}")
        return [f"{indent}{line}".rstrip() for line in lines]

    def keeps(self, record: str) -> bool:
        """Whether the handle keeps closures, for its methods to give"""

        return any(
            a.lifetime == "handle" and a.kind == "callback"
            for call in self.idioms.of(record)["method"]
            for a in call.args
            if self.usable(call) is None
        )

    def unusable(self, call: Call, reason: str) -> List[str]:
        raw = self.raw.fn_names[call.function]
        return [
            "",
            f"// {call.function}() has no idiomatic form, as {reason}; see {raw}.",
        ]

    def handle(self, record: str) -> List[str]:
        calls = self.idioms.of(record)
        struct = self.structs[record]
        raw = self.namer.type_name(types.Record(tag="struct", name=record))
        entity = self.model.find(record, decls.RECORDS)
        destructor = calls["destructor"][0] if calls["destructor"] else None
        released = (
            f"released by {self.fn_names[destructor.function]}, which calls"
            f" {destructor.function}"
            if destructor and self.usable(destructor) is None
            else "which nothing here releases"
        )
        lines = [""] + doc(
            doc_lines(entity.doc), f"{struct} owns a *{raw}, {released}."
        )
        fields: List[Tuple[List[str], List[str]]] = [([], ["ptr", f"*{raw}"])]
        if self.keeps(record):
            fields.append(([], ["keep", "[]unsafe.Pointer"]))
        lines += [f"type {struct} struct {{"] + ggen.align(fields) + ["}"]
        lines += [
            "",
            f"// Ptr is the raw pointer, still owned by the {struct}",
            f"func (h *{struct}) Ptr() *{raw} {{",
            "\treturn h.ptr",
            "}",
        ]
        for call in calls["constructor"] + calls["method"] + calls["destructor"]:
            reason = self.usable(call)
            lines += (
                self.unusable(call, reason) if reason else [""] + self.function(call)
            )
        return lines

    def trampolines(self) -> Tuple[List[str], List[str], List[str]]:
        """The C declarations of the trampolines, for the preamble, their C
        definitions, and the Go functions they call, exported to C"""

        decls_: List[str] = []
        defs: List[str] = []
        exports: List[str] = []
        for cname, closure in self.callbacks.items():
            func = self.callback_type(types.TypedefRef(name=cname))
            params = [cgen.decl(p.typ, f"a{i}") for i, p in enumerate(func.params)]
            ret = cgen.decl(func.ret)
            signature = cgen.decl(
                func.ret, f"yace_{cname}({', '.join(params) or 'void'})"
            )
            decls_.append(f"{signature};")
            passed: List[str] = []
            go_params: List[str] = []
            go_args: List[str] = []
            for i, p in enumerate(func.params):
                kind = self.namer.kind(p.typ)
                if is_void_ptr(p.typ):
                    passed.insert(0, f"a{i}")
                    go_params.insert(0, "ctx unsafe.Pointer")
                    continue
                if kind == "pointer":
                    passed.append(f"(void *)a{i}")
                    go_params.append(f"a{i} unsafe.Pointer")
                    if types.is_string(p.typ):
                        go_args.append(f"C.GoString((*C.char)(a{i}))")
                    elif self.namer.gotype(p.typ, True) == "unsafe.Pointer":
                        go_args.append(f"a{i}")
                    else:
                        go_args.append(f"({self.namer.gotype(p.typ, True)})(a{i})")
                else:
                    passed.append(f"a{i}")
                    go_params.append(f"a{i} {self.namer.ctype(p.typ)}")
                    go_args.append(self.namer.from_c(p.typ, f"a{i}"))
            call = f"yace_go_{cname}({', '.join(passed)})"
            rkind = self.namer.kind(func.ret)
            body = f"\t{call};" if rkind == "none" else f"\treturn ({ret}){call};"
            defs += ["", signature, "{", body, "}"]

            gocall = f"yaceCalled(ctx).({closure})({', '.join(go_args)})"
            if rkind == "none":
                gret, gbody = "", gocall
            elif rkind == "pointer":
                gret = " unsafe.Pointer"
                gbody = f"return unsafe.Pointer({gocall})"
            else:
                gret = f" {self.namer.ctype(func.ret)}"
                gbody = f"return {self.namer.ctype(func.ret)}({gocall})"
            exports += [
                "",
                f"//export yace_go_{cname}",
                f"func yace_go_{cname}({', '.join(go_params)}){gret} {{",
                f"\t{gbody}",
                "}",
            ]
        return decls_, defs, exports

    def render(self) -> List[str]:
        lines = [""] + HELPERS.splitlines()
        if self.callbacks:
            lines += [""] + CLOSURES.splitlines()
        for cname, closure in self.callbacks.items():
            go = self.namer.type_name(types.TypedefRef(name=cname))
            lines += [
                "",
                f"// {closure} is a function given as a {go}, without its context",
                f"type {closure} {self.closure_type(cname)}",
            ]
        for record in self.handles:
            lines += self.handle(record)
        for call in self.idioms.functions():
            reason = self.usable(call)
            lines += (
                self.unusable(call, reason) if reason else [""] + self.function(call)
            )
        lines += self.trampolines()[2]
        return lines
