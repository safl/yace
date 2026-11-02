"""
The idiomatic Python layer of the bindings, over the raw functions: handles as
classes that are context managers, errors as :py:class:`OSError`, what is
written through ``[out]`` pointers returned, sequences for arrays, callables
for callbacks, and str for strings. See :py:mod:`yace.targets.idiom` for what
is derived from where.
"""

import keyword
from functools import cached_property
from typing import List

from yace.ir import decls, types
from yace.ir.semantics import is_void_ptr
from yace.targets.idiom import (
    Call,
    Idioms,
    copyable,
    is_opaque_ptr,
    local,
    typedefs_used,
)

from . import pygen

# What the body of a function binds, which a parameter may not be named
BOUND = {"self", "ret", "ctypes", "enum"}


class Renderer(object):
    def __init__(self, idioms: Idioms, namer: pygen.Namer):
        self.idioms = idioms
        self.namer = namer
        self.classes: List[str] = []  # the handles with a class

    @cached_property
    def reserved(self) -> set:
        """What a body names unqualified: what it binds, and the module's own
        names, as of the raw function it calls, a type, among them those from
        other headers, or a class it returns"""

        model = self.idioms.model.entities
        found = BOUND | {pygen.ident(e.name) for e in model if hasattr(e, "name")}
        found |= set(self.namer.names.values())
        found |= {self.namer(n) for n in typedefs_used(model)}
        return found | {self.class_name(h) for h in self.idioms.handles}

    def pname(self, name: str) -> str:
        """A parameter's name, other than a keyword or a name the body uses; one
        starting or ending in '_' gets another, so no two parameters, and no
        name of the module's own, share a name"""

        if (
            keyword.iskeyword(name)
            or name in self.reserved
            or name.startswith("_")
            or name.endswith("_")
        ):
            return f"{name}_"
        return name

    def local(self, call: Call, param: str, suffix: str) -> str:
        """The local made for 'param', other than the name of a parameter or of
        what the body names unqualified"""

        taken = {self.pname(a.param) for a in call.args} | self.reserved
        return local(self.pname(param), suffix, taken)

    def class_name(self, handle: str) -> str:
        """The name of a handle's class, other than that of any raw type"""

        name = pygen.camel(self.idioms.handle_name(handle))
        if name in self.namer.names.values() or name in self.namer.stubs.values():
            name += "Handle"
        return pygen.ident(name)

    def doc(self, call: Call, indent: str) -> str:
        func = self.idioms.decl(call.function)
        visible = {a.param for a in self.visible(call)}
        shown = func.doc.model_copy(
            update={
                "params": {k: v for k, v in func.doc.params.items() if k in visible}
            }
        )
        body = pygen.docstring(shown, indent)
        body = body or call.function
        return pygen.quoted(f"{body}\n\n{indent}Calls {call.function}().", indent)

    def callback(self, call: Call, arg) -> List[str]:
        """Wrap the closure given for 'arg' in the C callback type"""

        name = self.pname(arg.param)
        func = self.idioms.decl(call.function)
        cbtype = self.namer.ctype(func.params[arg.index].typ, True)
        fntype = self.namer.resolve(func.params[arg.index].typ)
        params = fntype.to.params
        names = [f"_a{i}" for i in range(len(params))]
        passed = []
        for i, param in enumerate(params):
            if is_void_ptr(param.typ):
                continue  # the context; the closure has its own
            if isinstance(param.typ, types.Pointer) and isinstance(
                param.typ.to, types.Record
            ):
                passed.append(f"{names[i]}.contents")
            elif types.is_string(param.typ):
                passed.append(f"_str_out({names[i]})")
            else:
                passed.append(names[i])
        made = self.local(call, arg.param, "c")
        return [
            f"{made} = {cbtype}()",
            f"if {name} is not None:",
            f"    {made} = {cbtype}(",
            f"        lambda {', '.join(names)}: {name}({', '.join(passed)})",
            "    )",
        ]

    def elem(self, typ) -> str:
        """The ctypes type of an element of an array, bytes for void"""

        if isinstance(typ, types.Builtin) and typ.name == "void":
            return "ctypes.c_char"
        return self.namer.ctype(typ)

    def size(self, call: Call, param: str) -> str:
        """The number of elements given as the sequence 'param'"""

        arg = next(a for a in call.args if a.param == param)
        seq = self.pname(param)
        return (
            f"0 if {seq} is None else _builtins.len({seq})"
            if arg.nullable
            else f"_builtins.len({seq})"
        )

    def dispatcher(self, call: Call, arg) -> str:
        """The C callback, made once, that calls the closure kept under the key
        the library gives back as the context; called once, the key is dropped"""

        func = self.idioms.decl(call.function)
        cbtype = self.namer.ctype(func.params[arg.index].typ, True)
        key = (cbtype, arg.lifetime)
        if key not in self.dispatchers:
            fntype = self.namer.resolve(func.params[arg.index].typ)
            names = [f"a{i}" for i in range(len(fntype.to.params))]
            passed, ctx = [], None
            for i, param in enumerate(fntype.to.params):
                if is_void_ptr(param.typ):
                    ctx = names[i]
                elif isinstance(param.typ, types.Pointer) and isinstance(
                    param.typ.to, types.Record
                ):
                    passed.append(f"{names[i]}.contents")
                elif types.is_string(param.typ):
                    passed.append(f"_str_out({names[i]})")
                else:
                    passed.append(names[i])
            name = f"_kept{len(self.dispatchers)}"
            get = f"_KEPT.pop({ctx})" if arg.lifetime == "once" else f"_KEPT[{ctx}]"
            self.dispatchers[key] = (
                f"def {name}({', '.join(names)}):\n"
                f"    return {get}({', '.join(passed)})\n\n\n"
                f"{name}_c = {cbtype}({name})"
            )
        return self.dispatchers[key].splitlines()[-1].split(" = ")[0]

    def keep(self, call: Call, arg) -> List[str]:
        """Keep the closure given for 'arg', under a key to give as its context"""

        name = self.pname(arg.param)
        key = self.local(call, arg.param, "key")
        lines = [
            f"{key} = _builtins.next(_KEYS)",
            f"_KEPT[{key}] = {name}",
        ]
        if arg.lifetime == "handle":
            lines.append(f"self._keys.append({key})")
        return [f"{key} = None", f"if {name} is not None:"] + [
            f"    {line}" for line in lines
        ]

    def body(self, call: Call) -> List[str]:
        func = self.idioms.decl(call.function)
        pre: List[str] = []
        args: List[str] = []
        for arg in call.args:
            name = self.pname(arg.param)
            typ = func.params[arg.index].typ
            if arg.kind == "self":
                # Before any closure is kept, so a closed handle keeps none
                pre.insert(0, "_ptr = self._ptr")
                args.append("_ptr")
            elif arg.kind == "value" and is_opaque_ptr(typ, self.idioms.handles) in (
                self.classes
            ):
                ptr = f"{name}._ptr"
                args.append(
                    f"None if {name} is None else {ptr}" if arg.nullable else ptr
                )
            elif arg.kind in ("value", "string", "capacity"):
                args.append(name)
            elif arg.kind == "sequence" and is_void_ptr(typ):
                array = (
                    f"(ctypes.c_char * _builtins.len({name}))"
                    f".from_buffer_copy(_builtins.bytes({name}))"
                )
                if func.params[arg.index].direction == "inout":
                    array = (
                        f"(ctypes.c_char * _builtins.len({name})).from_buffer({name})"
                    )
                if arg.nullable:
                    array = f"None if {name} is None else {array}"
                pre.append(f"{self.local(call, arg.param, 'c')} = {array}")
                args.append(self.local(call, arg.param, "c"))
            elif arg.kind == "sequence":
                elem = self.namer.ctype(typ.to)
                array = f"({elem} * _builtins.len({name}))(*{name})"
                if arg.nullable:
                    array = f"None if {name} is None else {array}"
                pre.append(f"{self.local(call, arg.param, 'c')} = {array}")
                args.append(self.local(call, arg.param, "c"))
            elif arg.kind == "length":
                args.append(self.size(call, arg.of))
            elif arg.kind == "callback" and arg.lifetime in ("once", "handle"):
                pre += self.keep(call, arg)
                cbtype = self.namer.ctype(typ, True)
                disp = self.dispatcher(call, arg)
                key = self.local(call, arg.param, "key")
                args.append(f"{disp} if {key} else {cbtype}()")
            elif arg.kind == "callback":
                pre += self.callback(call, arg)
                args.append(self.local(call, arg.param, "c"))
            elif arg.kind == "context":
                owner = next(a for a in call.args if a.param == arg.of)
                if owner.lifetime in ("once", "handle"):
                    args.append(self.local(call, arg.of, "key"))
                else:
                    made = self.local(call, arg.of, "c")
                    args.append(f"ctypes.cast({made}, ctypes.c_void_p)")
            elif arg.kind == "out":
                out = next(o for o in call.outs if o.param == arg.param)
                if out.kind == "array":
                    elem = self.elem(out.typ)
                    pre.append(f"{name} = ({elem} * {self.pname(out.capacity)})()")
                    args.append(name)
                elif out.kind == "handle":
                    pre.append(f"{name} = {self.namer.ctype(out.typ)}()")
                    args.append(f"ctypes.byref({name})")
                elif out.kind == "record":
                    pre.append(f"{name} = {self.namer.ctype(out.typ)}()")
                    args.append(name)
                else:
                    pre.append(f"{name} = {self.namer.ctype(out.typ)}()")
                    args.append(f"ctypes.byref({name})")

        checks: List[str] = []
        for arg in call.args:
            if arg.kind in ("length", "capacity"):
                count = (
                    self.size(call, arg.of)
                    if arg.kind == "length"
                    else self.pname(arg.param)
                )
                for other in arg.shared:
                    if next(a for a in call.args if a.param == other).kind == "out":
                        continue
                    checks += [
                        f"if {self.size(call, other)} != {count}:",
                        f"    raise ValueError(\"'{other}' does not have the"
                        f" count '{arg.param}' of '{arg.of}'\")",
                    ]
        pre = checks + pre
        raw = pygen.ident(call.function)
        lines = pre + [f"ret = {raw}({', '.join(args)})"]
        if call.errno:
            for arg in call.args:
                if arg.kind == "callback" and arg.lifetime in ("once", "handle"):
                    key = self.local(call, arg.param, "key")
                    lines.append(f"if ret < 0 and {key}:")
                    lines.append(f"    _KEPT.pop({key}, None)")
                    if arg.lifetime == "handle":
                        lines.append(f"    self._keys.remove({key})")
            lines.append("_check(ret)")
        for arg in call.args:
            if (
                arg.kind == "sequence"
                and func.params[arg.index].direction == "inout"
                and not is_void_ptr(arg.typ)
            ):
                name = self.pname(arg.param)
                back = f"{name}[:] = {self.local(call, arg.param, 'c')}[:]"
                if arg.nullable:
                    lines += [f"if {name} is not None:", f"    {back}"]
                else:
                    lines.append(back)

        results = []
        count = "ret" if call.returns == "count" else None
        for out in call.outs:
            name = self.pname(out.param)
            if out.kind == "array":
                results.append(f"{name}[: {count or self.pname(out.capacity)}]")
                count = None  # the count is that of the array, not returned too
            elif out.kind == "handle":
                results.append(f"{self.class_name(out.typ.to.name)}({name})")
            elif out.kind == "record":
                results.append(name)
            elif self.points_to_value(out.typ):
                results.append(f"None if not {name} else {self.copy(out.typ, name)}")
            elif types.is_string(out.typ):
                results.append(f"_str_out({name}.value)")
            elif isinstance(out.typ, types.Pointer) and not is_void_ptr(out.typ):
                results.append(f"{name} or None")  # opaque, such as a FILE *
            else:
                results.append(f"{name}.value")
        if count:
            results.append("ret")
        if call.returns in ("value", "string"):
            results.append("ret")
        elif call.returns == "handle" and call.ret.to.name in self.classes:
            cls = self.class_name(call.ret.to.name)
            results.append(f"None if not ret else {cls}(ret, owned=False)")
        elif call.returns == "handle":
            results.append("ret")
        elif (
            call.returns == "pointer"
            and self.points_to_value(call.ret)
            and copyable(self.idioms.model, call.ret.to)
        ):
            results.append(f"None if not ret else {self.copy(call.ret, 'ret')}")
        elif call.returns == "pointer":
            results.append("ret")

        if not results:
            return lines
        if len(results) == 1:
            return lines + [f"return {results[0]}"]
        return lines + [f"return ({', '.join(results)})"]

    def points_to_value(self, typ) -> bool:
        """Whether 'typ' is a pointer to a record or number, not a string"""

        return (
            isinstance(typ, types.Pointer)
            and isinstance(typ.to, (types.Record, types.Builtin))
            and not is_void_ptr(typ)
            and not types.is_string(typ)
        )

    def copy(self, ptr: types.Pointer, expr: str) -> str:
        """A copy of what the pointer 'expr' points to"""

        if isinstance(ptr.to, types.Record):
            return f"_builtins.type({expr}.contents).from_buffer_copy({expr}.contents)"
        return f"{expr}.contents.value"

    def visible(self, call: Call) -> list:
        return [
            a
            for a in call.args
            if a.kind in ("value", "string", "sequence", "callback", "capacity")
        ]

    def params(self, call: Call) -> List[str]:
        """The parameter list; nullable ones default to None, where all after
        them do too"""

        found = []
        for arg in reversed(self.visible(call)):
            default = arg.nullable and all(p.endswith("=None") for p in found)
            found.append(self.pname(arg.param) + ("=None" if default else ""))
        return list(reversed(found))

    def function(self, call: Call, indent: str = "", self_: bool = False) -> str:
        params = (["self"] if self_ else []) + self.params(call)
        name = pygen.ident(call.name)
        own = call.kind == "constructor" and call.name == call.function
        if not self_ and (own or name in ("ctypes", "enum") or name.startswith("_")):
            name += "_"
        lines = [
            f"def {name}({', '.join(params)}):",
            f"    {self.doc(call, indent + '    ')}",
            "",
        ]
        lines += [f"    {line}" for line in self.body(call)]
        return "\n".join(f"{indent}{line}".rstrip() for line in lines)

    def handle(self, record: str) -> str:
        calls = self.idioms.of(record)
        cls = self.class_name(record)
        entity = self.idioms.model.find(record, decls.RECORDS)
        doc = pygen.docstring(entity.doc, "    ") or record
        destructor = calls["destructor"][0] if calls["destructor"] else None
        lines = [
            f"class {cls}(object):",
            f'    """{doc}',
            "",
            f"    Wraps a pointer to struct {record}, which it releases",
            (
                f"    with {destructor.name}(), also on leaving a with-block or when"
                "\n    collected,"
                if destructor
                else "    never: nothing releases it,"
            ),
            "    when it owns it.",
            '    """',
            "",
            "    def __init__(self, ptr, owned=True):",
            "        self._handle = ptr",
            "        self._owned = owned",
            "        self._keys = []",
            "",
            "    @property",
            "    def _ptr(self):",
            "        if not self._handle:",
            "            raise ValueError("
            f'"the {self.idioms.handle_name(record)} is closed")',
            "        return self._handle",
            "",
            "    def _release(self):",
            "        for key in self._keys:",
            "            _KEPT.pop(key, None)",
            "        self._keys = []",
            "",
            "    def __enter__(self):",
            "        return self",
            "",
            "    def __exit__(self, *exc):",
        ]
        if destructor:
            lines += [
                "        if self._owned and self._handle:",
                f"            self.{pygen.ident(destructor.name)}()",
            ]
        else:
            lines += ["        pass"]
        if destructor:
            lines += [
                "",
                "    def __del__(self):",
                "        if self._owned and self._handle:",
                f"            ret = {pygen.ident(destructor.function)}(self._handle)",
            ]
            if destructor.errno:
                lines += ["            if ret < 0:", "                self._keys = []"]
            lines += ["            self._release()"]
        for call in calls["method"]:
            lines += ["", self.function(call, "    ", self_=True)]
        if destructor:
            name = pygen.ident(destructor.name)
            lines += [
                "",
                f"    def {name}(self):",
                f"        {self.doc(destructor, '        ')}",
                "",
                "        if self._handle:",
                f"            ret = {pygen.ident(destructor.function)}(self._handle)",
                "            self._handle = None",
            ]
            if destructor.errno:
                lines += ["            if ret < 0:", "                self._keys = []"]
            lines += ["            self._release()"]
            if destructor.errno:
                lines.append("            _check(ret)")
        return "\n".join(lines)

    def usable(self, call: Call) -> bool:
        """Whether 'call' gets a name of its own: one only the raw layer has
        would replace the raw function it calls"""

        if call.kind == "function" and call.name == call.function:
            return False
        if call.handle is not None and call.kind != "function":
            return call.handle in self.classes
        return True

    def render(self) -> str:
        parts = [
            "def _check(ret):",
            '    """Raise the negative errno returned as an OSError"""',
            "",
            "    if ret < 0:",
            "        raise OSError(-ret, _os.strerror(-ret))",
        ]
        self.classes = [
            name for name in self.idioms.handles if any(self.idioms.of(name).values())
        ]
        self.dispatchers: dict = {}
        out = [self.handle(name) for name in self.classes]
        for call in self.idioms.calls:
            if call.kind == "constructor" and self.usable(call):
                out.append(self.function(call))
        out += [self.function(c) for c in self.idioms.functions() if self.usable(c)]
        if self.dispatchers:
            parts += [
                "",
                "",
                "_KEPT = {}",
                "_KEYS = __import__('itertools').count(1)",
            ]
        head = ["\n".join(parts)] + list(self.dispatchers.values())
        return "\n\n\n".join(head + out)
