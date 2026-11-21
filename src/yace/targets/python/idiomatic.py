# SPDX-FileCopyrightText: Simon A. F. Lund <os@safl.dk>
#
# SPDX-License-Identifier: GPL-2.0-only

"""
The idiomatic Python layer of the bindings, over the raw functions: handles as
classes that are context managers, errors as :py:class:`OSError`, what is
written through ``[out]`` pointers returned, sequences for arrays, callables
for callbacks, and str for strings. See :py:mod:`yace.targets.idiom` for what
is derived from where.
"""

import keyword
from functools import cached_property
from typing import List, Optional

from yace.ir import decls, types
from yace.ir.semantics import is_void_ptr
from yace.targets.idiom import (
    Call,
    Idioms,
    call_doc,
    copyable,
    is_opaque_ptr,
    local,
    typedefs_used,
)

from . import pygen

# What the body of a function binds, which a parameter may not be named
BOUND = {"self", "ret", "ctypes", "enum"}

# The roles of the functions that the objects of the buffer pattern call, not
# bound by names of their own
RELEASES = ("free", "realloc", "unregister")

BUFFER = '''class Buffer(object):
    """Memory the library allocated, freed by close(), on leaving a with-block,
    or when collected, and not while a view of it exists. Its bytes are given
    through the buffer protocol, so memoryview(), NumPy and PyTorch use them
    without a copy, and a function taking a buffer takes it. The memory may be
    a device's, which the CPU cannot read; close the buffer before what it was
    allocated with."""

    def __init__(self, address, nbytes, free, realloc=None):
        self._address = address
        self._nbytes = nbytes
        self._free = free
        self._realloc = realloc
        self._exports = 0

    @property
    def address(self):
        """The address of the memory"""

        if not self._address:
            raise ValueError("the buffer is closed")
        return self._address

    @property
    def nbytes(self):
        """The size of the memory in bytes"""

        return self._nbytes

    def __len__(self):
        return self._nbytes

    def __buffer__(self, flags):
        array = (ctypes.c_ubyte * self._nbytes).from_address(self.address)
        self._exports += 1
        return _builtins.memoryview(array).cast("B")

    def __release_buffer__(self, view):
        self._exports -= 1
        view.release()

    def realloc(self, nbytes):
        """Resize the buffer to 'nbytes' bytes, keeping its bytes up to the
        smaller size; its address may change"""

        if self._realloc is None:
            raise TypeError("the library does not resize this buffer")
        if self._exports:
            raise BufferError("a view of the buffer exists")
        address = self._realloc(self.address, nbytes)
        if not address:
            raise MemoryError(f"the buffer could not be resized to {nbytes} bytes")
        self._address, self._nbytes = address, nbytes

    def close(self):
        """Free the buffer; closing a closed buffer does nothing"""

        if self._exports:
            raise BufferError("a view of the buffer exists")
        if self._address:
            address, self._address = self._address, None
            self._free(address)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def __del__(self):
        if self._address:
            try:
                self._free(self._address)
            except ValueError:
                pass  # what it was allocated with is closed; it is not freed'''


REGISTRATION = '''class Registration(object):
    """Memory of the caller's that the library uses until close(), also called
    on leaving a with-block or when collected. It holds the object whose memory
    it is, so the memory is neither freed nor resized while registered."""

    def __init__(self, memory, unregister):
        self._memory = memory
        self._unregister = unregister

    @property
    def address(self):
        """The address of the memory"""

        if self._memory is None:
            raise ValueError("the registration is closed")
        return self._memory.address

    @property
    def nbytes(self):
        """The size of the memory in bytes"""

        return 0 if self._memory is None else self._memory.nbytes

    def close(self):
        """Unregister the memory; closing a closed registration does nothing.
        Where unregistering fails, the memory stays held."""

        if self._memory is not None:
            self._unregister(self._memory.address)
            memory, self._memory = self._memory, None
            memory.release()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def __del__(self):
        if self._memory is not None:
            try:
                self.close()
            except (OSError, ValueError):
                pass  # the memory stays held, as the library may use it'''


class Renderer(object):
    def __init__(self, idioms: Idioms, namer: pygen.Namer):
        self.idioms = idioms
        self.namer = namer
        self.classes: List[str] = []  # the handles with a class

    @cached_property
    def reserved(self) -> set:
        """What a body names unqualified: what it binds, and the module's own
        names, such as the raw function it calls, a type, among them the types
        of other headers, or a class it returns"""

        model = self.idioms.model.entities
        found = BOUND | {pygen.ident(e.name) for e in model if hasattr(e, "name")}
        found |= set(self.namer.names.values())
        found |= {self.namer(n) for n in typedefs_used(model)}
        return found | {self.class_name(h) for h in self.idioms.handles}

    def pname(self, name: str) -> str:
        """A parameter's name, other than a keyword or a name the body uses; one
        starting or ending in '_' gets another '_' appended, so no two
        parameters, and no name of the module's own, share a name"""

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
        shown, errors = call_doc(
            call,
            func.doc,
            self.pname,
            "The OSError holds what the call returns when it succeeds, as"
            " 'partial', with what was written before it failed.",
        )
        if self.registers(call):
            params = dict(shown.params)
            params.pop(self.pname(call.memory.nbytes), None)
            shown = shown.model_copy(update={"params": params})
        body = pygen.docstring(shown, indent, errors)
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
        if arg.kind == "sequence" and is_void_ptr(arg.typ):
            made = self.local(call, param, "m")
            return f"(0 if {made} is None else {made}.nbytes)"
        length = "_builtins.len"
        if arg.kind == "string":
            seq = f"_str_in({seq})"  # C counts the bytes of the encoded string
        return (
            f"0 if {seq} is None else {length}({seq})"
            if arg.nullable
            else f"{length}({seq})"
        )

    def dispatcher(self, call: Call, arg) -> str:
        """The C callback, made once, that calls the closure kept under the key
        the library gives back as the context; for a callback of @lifetime
        once, the dispatcher removes the key when called"""

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
        memories: List[str] = []  # the locals holding the memory of an object
        acquire: List[str] = []
        for arg in call.args:
            name = self.pname(arg.param)
            typ = func.params[arg.index].typ
            if arg.kind == "self":
                # Read before any closure is kept, so a closed handle raises
                # before it keeps one
                pre.insert(0, "_ptr = self._ptr")
                args.append("_ptr")
            elif arg.kind == "value" and is_opaque_ptr(typ, self.idioms.handles) in (
                self.classes
            ):
                ptr = f"{name}._ptr"
                args.append(
                    f"None if {name} is None else {ptr}" if arg.nullable else ptr
                )
            elif self.registers(call) and arg.param == call.memory.ptr:
                made = self.local(call, arg.param, "m")
                pre.append(f"{made} = _Memory({name}, True)")
                args.append(f"{made}.address")
            elif self.registers(call) and arg.param == call.memory.nbytes:
                made = self.local(call, call.memory.ptr, "m")
                args.append(f"_fits({made}.nbytes, {self.namer.ctype(typ)})")
            elif call.memory is not None and arg.param == call.memory.nbytes:
                # The size the buffer is made of; truncated, it would not be the
                # size of the memory
                args.append(f"_fits({name}, {self.namer.ctype(typ)})")
            elif arg.kind in ("value", "string"):
                args.append(name)
            elif arg.kind == "capacity":
                args.append(f"_fits({name}, {self.namer.ctype(typ)})")
            elif arg.kind == "sequence" and is_void_ptr(typ):
                made = self.local(call, arg.param, "m")
                writable = func.params[arg.index].direction == "inout"
                memories.append(made)
                acquire.append(
                    f"{made} = None if {name} is None else _Memory({name}, {writable})"
                    if arg.nullable
                    else f"{made} = _Memory({name}, {writable})"
                )
                args.append(
                    f"None if {made} is None else {made}.address"
                    if arg.nullable
                    else f"{made}.address"
                )
            elif arg.kind == "sequence":
                elem = self.namer.ctype(typ.to)
                array = f"({elem} * _builtins.len({name}))(*{name})"
                if arg.nullable:
                    array = f"None if {name} is None else {array}"
                pre.append(f"{self.local(call, arg.param, 'c')} = {array}")
                args.append(self.local(call, arg.param, "c"))
            elif arg.kind == "length":
                size = self.size(call, arg.of)
                args.append(f"_fits({size}, {self.namer.ctype(typ)})")
            elif arg.kind == "size":
                args.append(f"ctypes.sizeof({self.namer.ctype(call.sized(arg))})")
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
            elif arg.kind == "count":
                pre.append(f"{name} = {self.namer.ctype(arg.typ.to)}()")
                args.append(f"ctypes.byref({name})")
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
        pre = acquire + checks + pre
        raw = pygen.ident(call.function)
        lines = pre + [f"ret = {raw}({', '.join(args)})"]
        if self.registers(call):
            made = self.local(call, call.memory.ptr, "m")
            unregister = self.again(call, self.partner(call, "unregister"))
            cls = self.registration_class
            return lines + [
                "if ret < 0:",
                f"    {made}.release()",
                "_check(ret)",
                f"return {cls}({made}, {unregister})",
            ]
        if call.errno:
            for arg in call.args:
                if arg.kind == "callback" and arg.lifetime in ("once", "handle"):
                    key = self.local(call, arg.param, "key")
                    lines.append(f"if ret < 0 and {key}:")
                    lines.append(f"    _KEPT.pop({key}, None)")
                    if arg.lifetime == "handle":
                        lines.append(f"    self._keys.remove({key})")
            if not call.partial:
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
        counted: Optional[str] = "ret" if call.returns == "count" else None
        for out in call.outs:
            name = self.pname(out.param)
            if out.kind == "array":
                if out.count:
                    items = f"{name}[: {self.pname(out.count)}.value]"
                else:
                    items = f"{name}[: {counted or self.pname(out.capacity)}]"
                    counted = None  # the count is that of the array, not returned too
                elem = self.idioms.resolve(out.typ)
                to = self.idioms.resolve(getattr(elem, "to", None))
                if (
                    isinstance(elem, types.Pointer)
                    and isinstance(to, types.Record)
                    and not is_opaque_ptr(elem, self.idioms.handles)
                ):
                    # The records are the library's: views, which C is given
                    # back, or copies of const records
                    item = "p.contents"
                    const = elem.to.const or to.const
                    if const and copyable(self.idioms.model, to):
                        item = self.copy(types.Pointer(to=to), "p")
                    items = f"[{item} if p else None for p in {items}]"
                results.append(items)
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
        if counted:
            results.append("ret")
        if call.returns in ("value", "string"):
            results.append("ret")
        elif call.returns == "handle" and call.ret.to.name in self.classes:
            cls = self.class_name(call.ret.to.name)
            results.append(f"None if not ret else {cls}(ret, owned=False)")
        elif call.returns == "handle" and not is_opaque_ptr(
            call.ret, self.idioms.handles
        ):
            # A record lent to the caller: a view of the library's memory
            results.append("None if not ret else ret.contents")
        elif call.returns == "handle":
            results.append("ret")
        elif (
            call.returns == "pointer"
            and self.points_to_value(call.ret)
            and copyable(self.idioms.model, call.ret.to)
        ):
            results.append(f"None if not ret else {self.copy(call.ret, 'ret')}")
        elif call.returns == "pointer" and isinstance(call.ret.to, types.Record):
            # A copy would not hold all of the record: a view
            results.append("None if not ret else ret.contents")
        elif call.memory is not None and call.memory.role == "alloc":
            results.append(self.buffer(call))
        elif call.returns == "pointer":
            results.append("ret")

        if results:
            value = results[0] if len(results) == 1 else f"({', '.join(results)})"
            if call.partial:
                made = self.local(call, "partial", "value")
                lines += [f"{made} = {value}", f"_check(ret, {made})", f"return {made}"]
            else:
                lines.append(f"return {value}")
        if not memories:
            return lines
        # The memory is held until the call returns, also where it raises
        held = [f"{made} = None" for made in memories]
        released = []
        for made in memories:
            released += [f"    if {made} is not None:", f"        {made}.release()"]
        return (
            held
            + ["try:"]
            + [f"    {line}" for line in lines]
            + ["finally:"]
            + released
        )

    def partner(self, call: Call, role: str) -> Optional[Call]:
        """The call of the role 'role' in the buffer pattern of 'call'"""

        stem = call.memory.stem if call.memory else None
        return next(
            (
                c
                for c in self.idioms.calls
                if c.memory and c.memory.stem == stem and c.memory.role == role
            ),
            None,
        )

    def again(self, call: Call, partner: Optional[Call], nbytes: str = "") -> str:
        """A function of '_p', the address, calling the raw function of
        'partner' with what 'call' was called with, and 'nbytes' as the new
        size; None where 'partner' takes what 'call' was not given as a value"""

        if partner is None or partner.memory is None:
            return "None"
        given = {a.param: a for a in call.args}
        passed = []
        for param in self.idioms.decl(partner.function).params:
            arg = given.get(param.name)
            if param.name == partner.memory.ptr:
                passed.append("_p")
            elif param.name == partner.memory.nbytes:
                passed.append(f"_fits({nbytes}, ctypes.c_size_t)")
            elif arg is not None and arg.kind == "self":
                passed.append("self._ptr")
            elif arg is not None and arg.kind == "value":
                name = self.pname(arg.param)
                handle = is_opaque_ptr(arg.typ, self.idioms.handles)
                if handle in self.classes:
                    name = f"None if {name} is None else {name}._ptr"
                passed.append(name)
            else:
                return "None"
        raw = f"{pygen.ident(partner.function)}({', '.join(passed)})"
        params = "_p, _n" if nbytes else "_p"
        return f"lambda {params}: {f'_check({raw})' if partner.errno else raw}"

    def buffer(self, call: Call) -> str:
        """The Buffer of the memory 'call' allocated"""

        nbytes = self.pname(call.memory.nbytes)
        free = self.again(call, self.partner(call, "free"))
        realloc = self.again(call, self.partner(call, "realloc"), "_n")
        cls = self.buffer_class
        return f"None if not ret else {cls}(ret, {nbytes}, {free}, {realloc})"

    @cached_property
    def buffer_class(self) -> str:
        """The name of the class of an allocated buffer: Buffer, or Buffer_
        where a type or a handle of the API is named Buffer"""

        taken = set(self.namer.names.values())
        taken |= {self.class_name(h) for h in self.idioms.handles}
        return "Buffer_" if "Buffer" in taken else "Buffer"

    def registers(self, call: Call) -> bool:
        """Whether 'call' registers memory, and the layer can unregister it"""

        return (
            call.memory is not None
            and call.memory.role == "register"
            and self.again(call, self.partner(call, "unregister")) != "None"
        )

    @cached_property
    def registration_class(self) -> str:
        """The name of the class of a registration: Registration, or
        Registration_ where a type or a handle of the API is named so"""

        taken = set(self.namer.names.values())
        taken |= {self.class_name(h) for h in self.idioms.handles}
        return "Registration_" if "Registration" in taken else "Registration"

    def bound(self, call: Call) -> bool:
        """Whether 'call' is bound by a name of its own, not only through the
        object of the buffer pattern that calls it. A realloc the Buffer cannot
        call is not bound either, as it would free memory the Buffer owns."""

        if call.memory is None or call.memory.role not in RELEASES:
            return True
        role = "register" if call.memory.role == "unregister" else "alloc"
        owner = self.partner(call, role)
        if owner is None:
            return True
        release: Optional[Call] = call
        if call.memory.role == "realloc":
            release = self.partner(owner, "free")
        return self.again(owner, release) == "None"

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
        given = call.given()
        if self.registers(call):
            # The size is that of the memory of the object given
            given = [a for a in given if a.param != call.memory.nbytes]
        return given

    def params(self, call: Call) -> List[str]:
        """The parameter list; nullable ones default to None, where all after
        them do too"""

        found: List[str] = []
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
        if destructor:
            wraps = [
                f"    Wraps a pointer to struct {record}, which it releases",
                f"    with {destructor.name}(), also on leaving a with-block or when",
                "    collected,",
                "    when it owns it.",
            ]
        else:
            wraps = [f"    Wraps a pointer to struct {record}, which nothing releases."]
        lines = [
            f"class {cls}(object):",
            f'    """{doc}',
            "",
            *wraps,
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
            if self.bound(call):
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
        # The message of the library where the meta names the function that
        # returns it and the function returns one, else the message of the errno
        errmsg = self.idioms.model.errmsg()
        message = f"{pygen.ident(errmsg.name)}() or " if errmsg else ""
        parts = [
            "def _check(ret, *partial):",
            '    """Raise the negative errno returned as an OSError; with \'partial\',',
            '    the OSError holds it as what the call wrote before it failed"""',
            "",
            "    if ret < 0:",
            f"        error = OSError(-ret, {message}_os.strerror(-ret))",
            "        if partial:",
            "            error.partial = partial[0]",
            "        raise error",
        ]
        self.classes = [
            name for name in self.idioms.handles if any(self.idioms.of(name).values())
        ]
        self.dispatchers: dict = {}
        out = [self.handle(name) for name in self.classes]
        for call in self.idioms.calls:
            if call.kind == "constructor" and self.usable(call):
                out.append(self.function(call))
        out += [
            self.function(c)
            for c in self.idioms.functions()
            if self.usable(c) and self.bound(c)
        ]
        if self.dispatchers:
            parts += [
                "",
                "",
                "_KEPT = {}",
                "_KEYS = __import__('itertools').count(1)",
            ]
        head = ["\n".join(parts)] + list(self.dispatchers.values())
        if any(c.memory and c.memory.role == "alloc" for c in self.idioms.calls):
            cls = f"class {self.buffer_class}(object):"
            head.append(BUFFER.replace("class Buffer(object):", cls, 1))
        if any(self.registers(c) for c in self.idioms.calls):
            cls = f"class {self.registration_class}(object):"
            head.append(REGISTRATION.replace("class Registration(object):", cls, 1))
        return "\n\n\n".join(head + out)
