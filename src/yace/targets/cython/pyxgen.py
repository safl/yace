# SPDX-FileCopyrightText: Simon A. F. Lund <os@safl.dk>
#
# SPDX-License-Identifier: GPL-2.0-only

"""
Code of the Cython module of the bindings. The module provides the idiomatic
API of the Python target, compiled, and calls C through the ``.pxd`` instead
of through ctypes. A record is an extension type that holds the C struct, an
array is a buffer, and a handle is an extension type that releases the C
handle when its last reference is dropped. See :py:mod:`yace.targets.idiom`
for how each idiom is derived from the header.

Cython pairs the module with the ``.pxd`` of the same name, so the C names
that the ``.pxd`` declares are names of the module. A Python name that the
``.pxd`` also declares is defined under another name and then bound to the
Python name in the module's globals.
"""

import builtins
import keyword
from functools import cached_property
from typing import Dict, List, Optional, Tuple

from yace.ir import decls, types
from yace.ir.model import Model
from yace.ir.semantics import is_void_ptr
from yace.targets.capi import cgen
from yace.targets.idiom import (
    Call,
    Idioms,
    call_doc,
    copyable,
    is_opaque_ptr,
    local,
)
from yace.targets.python import pygen

from . import cygen

# The names a generated function body binds or calls. A parameter of one of
# these names is renamed.
BOUND = {
    "self",
    "ret",
    "enum",
    "cython",
    "i",
    "range",
    "bytearray",
    "free",
    "memset",
    "uintptr_t",
    "Py_buffer",
    "PyBuffer_Release",
    "PyObject_Length",
}

# The struct format character of an array element, by C type, as the buffer
# protocol reports it
FORMATS = {
    "bool": "?",
    "char": "b",
    "signed char": "b",
    "unsigned char": "B",
    "short": "h",
    "unsigned short": "H",
    "int": "i",
    "unsigned int": "I",
    "long": "l",
    "unsigned long": "L",
    "long long": "q",
    "unsigned long long": "Q",
    "float": "f",
    "double": "d",
    "int8_t": "b",
    "int16_t": "h",
    "int32_t": "i",
    "int64_t": "q",
    "uint8_t": "B",
    "uint16_t": "H",
    "uint32_t": "I",
    "uint64_t": "Q",
    "intptr_t": "n",
    "uintptr_t": "N",
    "size_t": "N",
    "ssize_t": "n",
    "ptrdiff_t": "n",
}


def kind_of(fmt: str) -> str:
    """Return the kind of element that the struct format 'fmt' describes: 'i'
    signed, 'u' unsigned, 'f' floating, 'b' bool or 'p' pointer. A buffer given
    for an array must have elements of the kind of the array."""

    if fmt == "?":
        return "b"
    if fmt in "fd":
        return "f"
    if fmt == "P":
        return "p"
    return "u" if fmt.isupper() else "i"


class Renderer(object):
    def __init__(self, model: Model, pxd: cygen.Pxd, namer: pygen.Namer):
        self.model = model
        self.idioms = Idioms(model)
        self.names = pxd.names
        self.namer = namer
        self.classes: List[str] = []  # the handles with a class
        # The name and the code of each trampoline, by callback type and lifetime
        self.trampolines: Dict[Tuple[str, Optional[str]], Tuple[str, str]] = {}
        self.records = {
            r.name: r for r in cgen.ordered_records(model) if self.has_class(r)
        }

    # Names

    @cached_property
    def cnames(self) -> set:
        """The names that the .pxd declares. Cython makes them names of the
        module too."""

        names = self.names
        found = set(names.names.values()) | set(names.tags.values())
        return found | set(names.stub_types.values()) | set(names.stub_tags.values())

    def pyname(self, name: str) -> str:
        """Return the name under which the module defines its own 'name':
        '_yace_<name>' where 'name' is declared by the .pxd, a builtin, or
        reserved by Cython, else 'name'. The generated code calls builtins, so
        the module may not redefine one."""

        if name in self.cnames or hasattr(builtins, name) or cygen.reserved(name):
            return f"_yace_{name}"
        return name

    def class_of(self, record: str) -> str:
        """Return the name of the class of 'record': the name the Python target
        gives the class, with '_' appended where the .pxd declares that name"""

        name = self.namer(record)
        return f"{name}_" if name in self.cnames else name

    @cached_property
    def reserved(self) -> set:
        """The names a generated function body may refer to: the names in
        BOUND, the names of the .pxd and the module's own names"""

        found = BOUND | self.cnames | set(self.namer.names.values())
        found |= {self.class_of(r) for r in self.records}
        return found | {self.handle_class(h) for h in self.idioms.handles}

    def pname(self, name: str) -> str:
        """Return the name of the parameter 'name', with '_' appended where
        'name' is a keyword, is reserved by Cython, is used by the body, or
        starts or ends with '_'"""

        if (
            keyword.iskeyword(name)
            or cygen.reserved(name)
            or name in self.reserved
            or name.startswith("_")
            or name.endswith("_")
        ):
            return f"{name}_"
        return name

    def local(self, call: Call, param: str, suffix: str) -> str:
        taken = {self.pname(a.param) for a in call.args} | self.reserved
        return local(self.pname(param), suffix, taken)

    def handle_class(self, handle: str) -> str:
        name = pygen.camel(self.idioms.handle_name(handle))
        taken = set(self.namer.names.values()) | set(self.namer.stubs.values())
        if name in taken or name in self.cnames:
            name += "Handle"
        return pygen.ident(name)

    # Types

    def decl(self, typ, inner: str = "") -> str:
        return self.names.decl(typ, inner)

    def cast(self, typ, spec: str = "noexcept nogil") -> str:
        """Return a cast to 'typ'. A function type within 'typ' is given
        'spec'. The default is what Cython gives the functions that the .pxd
        declares. Cython does not declare a field of function pointer type
        nogil, so the cast of such a field passes 'noexcept'."""

        return f"<{self.names.decl(typ, '', '', spec)}>"

    def resolve(self, typ):
        return self.namer.resolve(typ)

    def has_class(self, record) -> bool:
        return bool(record.name) and bool(record.fields)

    def record_class(self, typ) -> Optional[str]:
        """Return the class of the record that 'typ' resolves to, or None where
        the record has no class"""

        typ = self.resolve(typ)
        if isinstance(typ, types.Record) and typ.name in self.records:
            return self.class_of(typ.name)
        return None

    def mutable(self, typ):
        """Return 'typ' without its const"""

        return typ.model_copy(update={"const": False})

    def record_ptr(self, typ) -> str:
        """Return the declaration of a non-const pointer to the record 'typ',
        the type of the pointer that a view holds"""

        return self.decl(types.Pointer(to=self.mutable(typ)))

    def handle_of(self, typ) -> Optional[str]:
        """Return the class of the handle that 'typ' points to, or None where
        the handle has no class"""

        owned = is_opaque_ptr(typ, self.idioms.handles)
        return self.handle_class(owned) if owned in self.classes else None

    def fmt(self, typ) -> Optional[str]:
        """Return the struct format character of an element of type 'typ' in a
        buffer, or None where 'typ' has none"""

        typ = self.resolve(typ)
        if isinstance(typ, types.Builtin):
            return FORMATS.get(typ.name)
        if isinstance(typ, types.EnumRef):
            enum = self.model.enums().get(typ.name)
            if enum is not None and enum.underlying is not None:
                return self.fmt(enum.underlying)
            return "i"
        if isinstance(typ, types.Pointer) and not types.is_string(typ):
            return "P"
        return None

    def element_kind(self, typ) -> Optional[str]:
        """Return the kind of an element of type 'typ', as kind_of() gives it.
        An enum has the kind 'e', because the compiler chooses whether an enum
        is signed."""

        fmt = self.fmt(typ)
        if fmt is None:
            return None
        if isinstance(self.resolve(typ), types.EnumRef):
            return "e"
        return kind_of(fmt)

    # Conversions

    def to_py(self, typ, expr: str, owner: str = "None", copy: bool = False) -> str:
        """Return the code that converts the C expression 'expr' of type 'typ'
        to a Python value. A pointer to a record becomes a view that keeps
        'owner' alive, or with 'copy', a copy of the record. A pointer to a
        handle becomes an instance of the class of the handle that does not own
        the handle. Any other pointer becomes its address."""

        typ = self.resolve(typ)
        if types.is_string(typ) or (
            isinstance(typ, types.Pointer)
            and isinstance(self.resolve(typ.to), types.Builtin)
            and self.resolve(typ.to).name == "char"
        ):
            return f"_str_out({expr})"
        if isinstance(typ, types.Pointer):
            cls = self.handle_of(typ)
            if cls:
                return f"None if {expr} == NULL else {cls}._wrap({expr}, False)"
            cls = self.record_class(typ.to)
            if cls and copy:
                return f"None if {expr} == NULL else {cls}._copy({expr}[0])"
            if cls:
                view = f"{cls}._view(<{self.record_ptr(typ.to)}>{expr}, {owner})"
                return f"None if {expr} == NULL else {view}"
            if (
                copy
                and isinstance(self.resolve(typ.to), types.Builtin)
                and not is_void_ptr(typ)
            ):
                return f"None if {expr} == NULL else {expr}[0]"
            return f"_addr(<uintptr_t>{expr})"
        if isinstance(typ, types.Array):
            return f"_addr(<uintptr_t>{expr})"
        cls = self.record_class(typ)
        if cls:
            return f"{cls}._copy({expr})"
        return expr

    def to_c(self, typ, expr: str, nullable: bool = False) -> str:
        """Return the code that converts the Python value 'expr' to a C value
        of type 'typ'"""

        resolved = self.resolve(typ)
        if isinstance(resolved, types.Array):
            typ = resolved = types.Pointer(to=resolved.of)
        if isinstance(resolved, types.Pointer):
            cls = self.handle_of(resolved)
            if cls:
                value = f"(<{cls}?>{expr})._get()"
            elif self.record_class(resolved.to):
                cls = self.record_class(resolved.to)
                value = f"(<{cls}?>{expr})._yace_p"
            else:
                value = f"{self.cast(typ)}<uintptr_t>{expr}"
            return f"NULL if {expr} is None else {value}" if nullable else value
        cls = self.record_class(resolved)
        if cls:
            return f"(<{cls}?>{expr})._yace_p[0]"
        if isinstance(resolved, types.EnumRef):
            return f"{self.cast(typ)}<long long>{expr}"
        return expr

    # Functions

    def doc(self, call: Call, indent: str) -> str:
        func = self.idioms.decl(call.function)
        shown, errors = call_doc(
            call,
            func.doc,
            self.pname,
            "The OSError holds what the call returns when it succeeds, as"
            " 'partial', with what was written before it failed.",
        )
        body = pygen.docstring(shown, indent, errors) or call.function
        return pygen.quoted(f"{body}\n\n{indent}Calls {call.function}().", indent)

    def trampoline(self, call: Call, arg) -> str:
        """Return the name of the C function that calls the closure of the
        callback 'arg'. One function is made per callback type and lifetime.
        For a callback of @lifetime call, the context pointer is the closure.
        For the other lifetimes, the context is the key under which _KEPT keeps
        the closure, and the function of a callback of @lifetime once removes
        the key when called."""

        func = self.idioms.decl(call.function)
        cbtype = self.decl(func.params[arg.index].typ)
        lifetime = arg.lifetime if arg.lifetime in ("once", "handle") else None
        key = (cbtype, lifetime)
        if key in self.trampolines:
            return self.trampolines[key][0]

        fntype = self.resolve(func.params[arg.index].typ).to
        names = [f"a{i}" for i in range(len(fntype.params))]
        params, passed, ctx = [], [], "NULL"
        for name, param in zip(names, fntype.params):
            params.append(self.decl(param.typ, name))
            if is_void_ptr(param.typ):
                ctx = name
            else:
                passed.append(self.to_py(param.typ, name))
        name = f"_{'kept' if lifetime else 'call'}{len(self.trampolines)}"
        if lifetime == "once":
            closure = f"_KEPT.pop(<uintptr_t>{ctx})"
        elif lifetime == "handle":
            closure = f"_KEPT[<uintptr_t>{ctx}]"
        else:
            closure = f"(<object>{ctx})"
        made = f"{closure}({', '.join(passed)})"
        ret = self.resolve(fntype.ret)
        void = isinstance(ret, types.Builtin) and ret.name == "void"
        head = self.decl(fntype.ret, f"{name}({', '.join(params)})")
        body = made if void else f"return {self.to_c(fntype.ret, made)}"
        self.trampolines[key] = (name, f"cdef {head} noexcept with gil:\n    {body}")
        return name

    def sequence(self, call: Call, arg, cdefs, pre, after, releases) -> Tuple[str, str]:
        """Add the code that converts the sequence 'arg', and return the C
        pointer and the count of elements as expressions"""

        func = self.idioms.decl(call.function)
        param = func.params[arg.index]
        name = self.pname(arg.param)
        typ = self.resolve(param.typ)
        elem = typ.to if isinstance(typ, types.Pointer) else typ.of
        ptr = self.cast(types.Pointer(to=elem) if isinstance(typ, types.Array) else typ)
        written = param.direction == "inout"

        cls = self.record_class(elem)
        if cls:
            made = self.local(call, arg.param, "r")
            size = f"sizeof({self.decl(self.mutable(self.resolve(elem)))})"
            cdefs.append(f"cdef _Records {made}")
            pre.append(f"{made} = _records({name}, {cls}, {size})")
            if written:
                after.append(f"{made}.write_back()")
            return f"{ptr}{made}.buf", f"{made}.n"
        if types.is_string(self.resolve(elem)):
            made = self.local(call, arg.param, "s")
            cdefs.append(f"cdef _Strings {made}")
            pre.append(f"{made} = _strings({name})")
            return f"{ptr}{made}.ptrs", f"{made}.n"

        view = self.local(call, arg.param, "view")
        held = self.local(call, arg.param, "held")
        cdefs += [f"cdef Py_buffer {view}", f"cdef object {held} = None"]
        cdefs.append(f"memset(&{view}, 0, sizeof({view}))")
        if is_void_ptr(typ):
            kind, size = "v", "1"
        else:
            kind = self.element_kind(elem) or "p"
            size = f"sizeof({self.decl(self.mutable(elem))})"
        acquire = f"{held} = _acquire({name}, &{view}, b'{kind}', {size}, {written})"
        releases.append(f"PyBuffer_Release(&{view})")
        if arg.nullable:
            pre += [f"if {name} is not None:", f"    {acquire}"]
        else:
            pre.append(acquire)
        if written and kind != "v":
            # _acquire() copied a sequence that is not a buffer; write the copy back
            after += [
                f"if {held} is not None and {held} is not {name}:",
                f"    {name}[:] = {held}",
            ]
        count = f"{view}.len" if kind == "v" else f"{view}.len // {size}"
        return f"{ptr}{view}.buf", count

    def body(self, call: Call) -> List[str]:
        func = self.idioms.decl(call.function)
        cdefs: List[str] = []
        pre: List[str] = []
        after: List[str] = []  # in the try, after the call
        releases: List[str] = []
        args: List[str] = []
        counts: Dict[str, str] = {}  # sequence -> the count of its elements

        for arg in call.args:
            name = self.pname(arg.param)
            typ = func.params[arg.index].typ
            if arg.kind == "self":
                # Read first, so a closed handle raises before a closure is kept
                cdefs.insert(0, f"cdef {self.decl(typ, '_ptr')} = self._get()")
                args.append("_ptr")
            elif arg.kind == "value":
                args.append(self.to_c(typ, name, arg.nullable))
            elif arg.kind == "string":
                made = self.local(call, arg.param, "b")
                cdefs.append(f"cdef object {made} = _str_in({name})")
                counts[arg.param] = (
                    f"(0 if {made} is None else PyObject_Length({made}))"
                )
                args.append(f"{self.cast(typ)}_cstr({made})")
            elif arg.kind == "sequence":
                ptr, count = self.sequence(call, arg, cdefs, pre, after, releases)
                counts[arg.param] = count
                args.append(ptr)
            elif arg.kind == "length":
                args.append("")  # the count of its sequence, set below
            elif arg.kind == "size":
                args.append(f"sizeof({self.decl(call.sized(arg))})")
            elif arg.kind == "capacity":
                args.append(name)
            elif arg.kind == "callback":
                tramp = self.trampoline(call, arg)
                cbtype = self.cast(typ)
                if arg.lifetime in ("once", "handle"):
                    key = self.local(call, arg.param, "key")
                    lines = [f"{key} = _key()", f"_KEPT[{key}] = {name}"]
                    if arg.lifetime == "handle":
                        lines.append(f"self._keys.append({key})")
                    pre += [f"{key} = None", f"if {name} is not None:"]
                    pre += [f"    {line}" for line in lines]
                    args.append(f"NULL if {key} is None else {cbtype}{tramp}")
                else:
                    args.append(f"NULL if {name} is None else {cbtype}{tramp}")
            elif arg.kind == "context":
                owner = next(a for a in call.args if a.param == arg.of)
                if owner.lifetime in ("once", "handle"):
                    key = self.local(call, arg.of, "key")
                    args.append(f"NULL if {key} is None else <void *><uintptr_t>{key}")
                else:
                    oname = self.pname(owner.param)
                    args.append(f"NULL if {oname} is None else <void *>{oname}")
            elif arg.kind == "count":
                cdefs.append(f"cdef {self.decl(arg.typ.to, name)}")
                cdefs.append(f"memset(&{name}, 0, sizeof({name}))")
                args.append(f"&{name}")
            elif arg.kind == "out":
                args.append(self.out(call, arg, cdefs, pre, releases))

        # A length is passed as the count of its sequence. Every other sequence
        # that shares the length must have the same count.
        checks: List[str] = []
        for i, arg in enumerate(call.args):
            if arg.kind not in ("length", "capacity"):
                continue
            own = self.pname(arg.param)
            if arg.kind == "length":
                own = counts.get(arg.of) or "0"
                # Converted through a Python int, which raises OverflowError
                # where the type of the length cannot hold the count
                made = self.local(call, arg.param, "n")
                typ = self.mutable(func.params[arg.index].typ)
                cdefs.append(f"cdef {self.decl(typ, made)}")
                checks.append(f"{made} = <object>({own})")
                args[i] = made
            for other in arg.shared:
                if next(a for a in call.args if a.param == other).kind == "out":
                    continue
                checks += [
                    f"if {counts[other]} != {own}:",
                    f"    raise ValueError(\"'{other}' does not have the"
                    f" count '{arg.param}' of '{arg.of}'\")",
                ]

        ret = self.resolve(call.ret)
        void = isinstance(ret, types.Builtin) and ret.name == "void"
        raw = self.names.of(call.function)
        made = f"{raw}({', '.join(args)})"
        if not void:
            cdefs.append(f"cdef {self.decl(call.ret, 'ret')}")
            made = f"ret = {made}"

        # The try releases the buffers also where a check raises. The checks
        # follow the acquiring because they compare the counts of the buffers.
        lines = list(cdefs)
        if releases:
            lines += ["try:"] + [
                f"    {line}" for line in pre + checks + [made] + after
            ]
            lines += ["finally:"] + [f"    {line}" for line in releases]
        else:
            lines += pre + checks + [made] + after

        if call.errno:
            for arg in call.args:
                if arg.kind == "callback" and arg.lifetime in ("once", "handle"):
                    key = self.local(call, arg.param, "key")
                    lines.append(f"if ret < 0 and {key} is not None:")
                    lines.append(f"    _KEPT.pop({key}, None)")
                    if arg.lifetime == "handle":
                        lines.append(f"    self._keys.remove({key})")
            if not call.partial:
                lines.append("_check(ret)")

        results = self.results(call, lines)
        if not results:
            return lines
        value = results[0] if len(results) == 1 else f"({', '.join(results)})"
        if call.partial:
            partial = self.local(call, "partial", "value")
            return lines + [
                f"{partial} = {value}",
                f"_check(ret, {partial})",
                f"return {partial}",
            ]
        return lines + [f"return {value}"]

    def out(self, call: Call, arg, cdefs, pre, releases) -> str:
        """Add the code that allocates what the function writes through 'arg',
        and return the pointer expression passed to C"""

        name = self.pname(arg.param)
        out = call.out(arg.param)
        if out.kind == "array":
            cap = self.pname(out.capacity)
            elem = out.typ
            ptr = self.cast(types.Pointer(to=elem))
            if is_void_ptr(types.Pointer(to=elem)):
                cdefs.append(f"cdef bytearray {name}")
                pre.append(f"{name} = bytearray({cap})")
                return f"<void *><char *>{name}"
            if self.record_class(elem) or types.is_string(self.resolve(elem)):
                cdefs.append(f"cdef {self.decl(self.mutable(elem), '*' + name)} = NULL")
                size = f"sizeof({self.decl(self.mutable(elem))})"
                pre += [
                    f"{name} = {self.cast(types.Pointer(to=self.mutable(elem)))}"
                    f"_calloc({cap}, {size})"
                ]
                releases.append(f"free({name})")
                return f"{ptr}{name}"
            kind = self.element_kind(elem) or "p"
            size = f"sizeof({self.decl(self.mutable(elem))})"
            view = self.local(call, arg.param, "view")
            cdefs += [f"cdef object {name}", f"cdef Py_buffer {view}"]
            cdefs.append(f"memset(&{view}, 0, sizeof({view}))")
            pre += [
                f"{name} = _zeroed(b'{kind}', {size}, {cap})",
                f"_acquire({name}, &{view}, b'{kind}', {size}, True)",
            ]
            releases.append(f"PyBuffer_Release(&{view})")
            return f"{ptr}{view}.buf"
        if out.kind == "handle":
            cdefs.append(f"cdef {self.decl(out.typ, name)} = NULL")
            return f"&{name}"
        if out.kind == "record":
            cls = self.record_class(out.typ)
            cdefs.append(f"cdef {cls} {name} = {cls}.__new__({cls})")
            return f"{name}._yace_p"
        cdefs.append(f"cdef {self.decl(self.mutable(out.typ), name)}")
        cdefs.append(f"memset(&{name}, 0, sizeof({name}))")
        return f"&{name}"

    def results(self, call: Call, lines: List[str]) -> List[str]:
        results = []
        counted: Optional[str] = "ret" if call.returns == "count" else None
        for out in call.outs:
            name = self.pname(out.param)
            if out.kind == "array":
                cap = self.pname(out.capacity)
                if out.count:
                    count = self.pname(out.count)
                else:
                    count = counted or cap
                    counted = None  # 'ret' counts this array and is not returned too
                written = f"_bound({count}, {cap})"
                elem = out.typ
                if is_void_ptr(types.Pointer(to=elem)) or not (
                    self.record_class(elem) or types.is_string(self.resolve(elem))
                ):
                    lines.append(f"del {name}[{written}:]")
                    results.append(name)
                    continue
                # Converted in the try, before the array is freed
                value = self.to_py(elem, f"{name}[i]", copy=True)
                if self.record_class(elem):
                    value = f"{self.record_class(elem)}._copy({name}[i])"
                made = self.local(call, out.param, "items")
                index = next(i for i, line in enumerate(lines) if line == "finally:")
                lines[index:index] = [
                    f"    {made} = [{value} for i in range({written})]"
                ]
                results.append(made)
            elif out.kind == "handle":
                cls = self.handle_of(out.typ)
                if cls:
                    results.append(f"{cls}._wrap({name}, True)")
                else:
                    results.append(f"_addr(<uintptr_t>{name})")
            elif out.kind == "record":
                results.append(name)
            else:
                results.append(self.to_py(out.typ, name, copy=True))
        if counted:
            results.append("ret")
        if call.returns in ("value", "string"):
            results.append(self.to_py(call.ret, "ret"))
        elif call.returns == "handle":
            results.append(self.to_py(call.ret, "ret"))
        elif call.returns == "pointer":
            copy = copyable(self.model, call.ret.to)
            results.append(self.to_py(call.ret, "ret", copy=copy))
        return results

    def visible(self, call: Call) -> list:
        return call.given()

    def params(self, call: Call) -> List[str]:
        found: List[str] = []
        for arg in reversed(self.visible(call)):
            default = arg.nullable and all(p.endswith("=None") for p in found)
            found.append(self.pname(arg.param) + ("=None" if default else ""))
        return list(reversed(found))

    def public(self, call: Call, self_: bool = False) -> str:
        """Return the name of the function of 'call', or with 'self_' of the
        method, as the ctypes module names it"""

        name = pygen.ident(call.name)
        own = call.kind == "constructor" and call.name == call.function
        if not self_ and (
            own or name in ("ctypes", "enum", "cython") or name.startswith("_")
        ):
            name += "_"
        return name

    def function(self, call: Call, indent: str = "", self_: bool = False) -> str:
        params = (["self"] if self_ else []) + self.params(call)
        name = self.public(call, self_)
        defined = name if self_ else self.pyname(name)
        lines = [
            f"def {defined}({', '.join(params)}):",
            f"    {self.doc(call, indent + '    ')}",
            "",
        ]
        lines += [f"    {line}" for line in self.body(call)]
        text = "\n".join(f"{indent}{line}".rstrip() for line in lines)
        if defined != name:
            text += "\n\n\n" + bind(defined, name)
        return text

    def handle(self, record: str) -> str:
        calls = self.idioms.of(record)
        cls = self.handle_class(record)
        entity = self.model.find(record, decls.RECORDS)
        doc = pygen.docstring(entity.doc, "    ") or record
        destructor = calls["destructor"][0] if calls["destructor"] else None
        ptr = self.decl(
            types.Pointer(to=types.Record(tag=cgen.tag(entity), name=record))
        )
        if destructor:
            wraps = [
                f"    Wraps a pointer to struct {record}, which it releases",
                f"    with {destructor.name}(), also on leaving a with-block or when",
                "    collected, when it owns it.",
            ]
        else:
            wraps = [f"    Wraps a pointer to struct {record}, which nothing releases."]
        name = self.idioms.handle_name(record)
        lines = [
            "@cython.no_gc_clear",
            f"cdef class {cls}:",
            f'    """{doc}',
            "",
            *wraps,
            '    """',
            "",
            f"    cdef {ptr.replace('*', '*_handle', 1)}",
            "    cdef bint _owned",
            "    cdef readonly list _keys",
            "",
            "    def __cinit__(self):",
            "        self._keys = []",
            "",
            "    def __init__(self):",
            f'        raise TypeError("a {name} is made by calling the API")',
            "",
            "    @staticmethod",
            f"    cdef {cls} _wrap({ptr.replace('*', '*ptr', 1)}, bint owned):",
            f"        cdef {cls} made = {cls}.__new__({cls})",
            "        made._handle = ptr",
            "        made._owned = owned",
            "        return made",
            "",
            f"    cdef {ptr.replace('*', '*_get', 1)}(self) except NULL:",
            "        if self._handle == NULL:",
            f'            raise ValueError("the {name} is closed")',
            "        return self._handle",
            "",
            "    cdef _release(self):",
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
                "        if self._owned and self._handle != NULL:",
                f"            self.{pygen.ident(destructor.name)}()",
                "",
                "    def __dealloc__(self):",
                "        if self._owned and self._handle != NULL:",
            ]
            raw = self.names.of(destructor.function)
            if destructor.errno:
                lines += [
                    f"            if {raw}(self._handle) < 0:",
                    "                self._keys = []",
                ]
            else:
                lines.append(f"            {raw}(self._handle)")
            lines.append("            self._release()")
        else:
            lines.append("        pass")
        for call in calls["method"]:
            lines += ["", self.function(call, "    ", self_=True)]
        if destructor:
            raw = self.names.of(destructor.function)
            lines += [
                "",
                f"    def {pygen.ident(destructor.name)}(self):",
                f"        {self.doc(destructor, '        ')}",
                "",
                "        if self._handle != NULL:",
            ]
            if destructor.errno:
                lines += [
                    f"            ret = {raw}(self._handle)",
                    "            self._handle = NULL",
                    "            if ret < 0:",
                    "                self._keys = []",
                    "            self._release()",
                    "            _check(ret)",
                ]
            else:
                lines += [
                    f"            {raw}(self._handle)",
                    "            self._handle = NULL",
                    "            self._release()",
                ]
        return "\n".join(lines)

    def usable(self, call: Call) -> bool:
        if call.handle is not None and call.kind != "function":
            return call.handle in self.classes
        return True

    # Records

    def field(self, record, field: decls.Field) -> Optional[List[str]]:
        """Return the lines of the property of 'field', a getter and a setter,
        or None for a field the module does not bind"""

        attr = self.attr(field.name, record)
        member = f"self._yace_p.{cygen.field_name(field.name)}"
        typ = self.resolve(field.typ)
        doc = pygen.quoted(
            field.doc.brief and " ".join(field.doc.brief.split()) or field.name,
            "        ",
        )
        get: List[str]
        put: List[str]
        packed = bool(record.packed)
        if isinstance(typ, types.Array):
            dims = []
            elem = typ
            while isinstance(elem, types.Array):
                dims.append(elem.length or 0)
                elem = self.resolve(elem.of)
            cls = self.record_class(elem)
            if (
                len(dims) == 1
                and isinstance(elem, types.Builtin)
                and elem.name == "char"
            ):
                get = [f"return _chars(<const char *>{member}, {dims[0]})"]
                put = [f"_set_chars(<char *>{member}, {dims[0]}, value)"]
            elif cls and len(dims) == 1:
                put = [
                    "cdef Py_ssize_t i",
                    f"_check_length(value, {dims[0]})",
                    "for i, item in enumerate(value):",
                    f"    {member}[i] = (<{cls}?>item)._yace_p[0]",
                    *[
                        f"    {line}"
                        for line in self.adopt(elem, f"{member}[i]", "item")
                    ],
                ]
                if not packed:
                    get = [
                        "cdef Py_ssize_t i",
                        f"return tuple([{cls}._view(&{member}[i], self)"
                        f" for i in range({dims[0]})])",
                    ]
                else:
                    # The address of a packed field may be unaligned, so the
                    # getter returns copies
                    get = [
                        "cdef Py_ssize_t i",
                        f"cdef {cls} made",
                        "found = []",
                        f"for i in range({dims[0]}):",
                        *[f"    {line}" for line in self.copied(elem, f"{member}[i]")],
                        "    found.append(made)",
                        "return tuple(found)",
                    ]
            elif self.fmt(elem) and packed and len(dims) == 1:
                get = [
                    "cdef Py_ssize_t i",
                    f"return [{member}[i] for i in range({dims[0]})]",
                ]
                put = [
                    "cdef Py_ssize_t i",
                    f"_check_length(value, {dims[0]})",
                    "for i, item in enumerate(value):",
                    f"    {member}[i] = item",
                ]
            elif self.fmt(elem) and not packed:
                size = f"sizeof({self.decl(self.mutable(elem))})"
                shape = ", ".join(str(d) for d in dims)
                get = [
                    f'return _memory(self, <void *>{member}, b"{self.fmt(elem)}",'
                    f" {size}, ({shape},))"
                ]
                put = [f"_set_items(self.{attr}, value)"]
            else:
                return None
        elif isinstance(typ, types.Record):
            cls = self.record_class(typ)
            if cls is None:
                return None
            if packed:
                get = [f"cdef {cls} made", *self.copied(typ, member), "return made"]
            else:
                get = [f"return {cls}._view(&{member}, self)"]
            put = [
                f"{member} = (<{cls}?>value)._yace_p[0]",
                *self.adopt(typ, member, "value"),
            ]
        elif types.is_string(field.typ) or (
            isinstance(typ, types.Pointer)
            and isinstance(self.resolve(typ.to), types.Builtin)
            and self.resolve(typ.to).name == "char"
        ):
            get = [f"return _str_out({member})"]
            # _str_in() and _cstr() may raise, so they run before _yace_keep()
            # drops the string set earlier
            put = [
                "value = _str_in(value)",
                "cdef const char *made = _cstr(value)",
                f"self._yace_keep(&{member}, sizeof({member}), value)",
                f"{member} = {self.cast(field.typ)}made",
            ]
        elif isinstance(typ, types.Pointer):
            get = [f"return _addr(<uintptr_t>{member})"]
            put = [
                f"{member} = {self.cast(field.typ, 'noexcept')}<uintptr_t>(value or 0)"
            ]
        elif isinstance(typ, types.Builtin) and typ.name == "char":
            get = [f"return bytes([<unsigned char>{member}])"]
            put = [f"{member} = _char_in(value)"]
        elif isinstance(typ, types.EnumRef):
            get = [f"return {member}"]
            put = [f"{member} = {self.cast(field.typ)}<long long>value"]
        else:
            get = [f"return {member}"]
            put = [f"{member} = value"]
        lines = [
            "",
            "    @property",
            f"    def {attr}(self):",
            f"        {doc}",
            "",
            *[f"        {line}" for line in get],
            "",
            f"    @{attr}.setter",
            f"    def {attr}(self, value):",
            *[f"        {line}" for line in put],
        ]
        return lines

    def keeps(self, typ) -> bool:
        """Return whether 'typ' is a pointer to char, or an array or a record
        that contains one. A record keeps the object set to such a field for as
        long as the record lives."""

        typ = self.resolve(typ)
        while isinstance(typ, types.Array):
            typ = self.resolve(typ.of)
        if isinstance(typ, types.Pointer):
            to = self.resolve(typ.to)
            return isinstance(to, types.Builtin) and to.name == "char"
        if isinstance(typ, types.Record) and typ.name in self.records:
            return any(self.keeps(f.typ) for f in self.records[typ.name].fields)
        return False

    def adopt(self, typ, member: str, value: str) -> List[str]:
        """Return the code to run after the record 'value', of type 'typ', is
        copied to 'member'. The code keeps, for 'member', the objects that
        'value' keeps for its string fields."""

        if not self.keeps(typ):
            return []
        return [
            f"self._yace_adopt(&{member}, {value}, (<_Record>{value})._yace_vp,"
            f" sizeof({member}))"
        ]

    def copied(self, typ, member: str) -> List[str]:
        """Return the code that sets 'made' to a copy of the record of type
        'typ' at 'member'. The copy keeps the objects that 'self' keeps for the
        string fields of 'member'."""

        lines = [f"made = {self.record_class(typ)}._copy({member})"]
        if self.keeps(typ):
            lines.append(
                f"made._yace_adopt(made._yace_vp, self, &{member}, sizeof({member}))"
            )
        return lines

    def attr(self, name: str, record=None) -> str:
        """Return the attribute name of the field 'name'. A keyword or a name
        that Cython reserves gets '_' appended, repeated until no field of
        'record' has the resulting name."""

        if not (keyword.iskeyword(name) or cygen.reserved(name)):
            return name
        taken = {f.name for f in record.fields} if record is not None else set()
        found = f"{name}_"
        while found in taken:
            found += "_"
        return found

    def this(self, record) -> str:
        """The name of the record in its constructor: 'self', or '_self' where
        a field is named self."""

        taken = {f.name for f in record.fields}
        found = "self"
        while found in taken:
            found = f"_{found}"
        return found

    def kind(self, typ) -> Optional[str]:
        """Return how the printers print a field of type 'typ' where the Python
        value alone does not determine it: 'char' for a char, printed as its
        code, 'pointer' for a pointer, printed as its address, else None"""

        typ = self.resolve(typ)
        if isinstance(typ, types.Builtin) and typ.name == "char":
            return "char"
        while isinstance(typ, types.Array):
            typ = self.resolve(typ.of)
        if isinstance(typ, types.Pointer) and not (
            isinstance(self.resolve(typ.to), types.Builtin)
            and self.resolve(typ.to).name == "char"
        ):
            return "pointer"
        return None

    def record(self, record) -> str:
        cls = self.class_of(record.name)
        rtype = types.Record(tag=cgen.tag(record), name=record.name)
        ctype = self.decl(rtype)
        summary = pygen.docstring(record.doc, "    ") or (
            f"{cgen.tag(record)} {record.name}"
        )
        named = [f for f in record.fields if f.name and not self.flexible(f)]
        properties = {f.name: self.field(record, f) for f in named}
        fields = [f for f in named if properties[f.name] is not None]
        lines = [
            f"cdef class {cls}(_Record):",
            f'    """{summary}',
            "",
            "    Attributes:",
        ]
        for field in fields:
            brief = " ".join((field.doc.brief or field.name).split())
            lines.append(f"        {self.attr(field.name, record)}: {brief}")
        lines += ['    """', ""]
        lines.append(f'    _yace_name = "{record.name}"')
        pairs = ", ".join(
            f'("{f.name}", "{self.attr(f.name, record)}")' for f in fields
        )
        lines.append(f"    _yace_fields = ({pairs}{',' if len(fields) == 1 else ''})")
        kinds = {f.name: self.kind(f.typ) for f in fields if self.kind(f.typ)}
        if kinds:
            lines.append(f"    _yace_kinds = {kinds!r}")
        masked = [f for f in fields if f.masks]
        if masked:
            lines.append("    _yace_masks = {")
            for field in masked:
                parts = " ".join(
                    f'("{m.name}", {m.value:#x}, {m.lo}),' for m in field.masks
                )
                lines.append(f'        "{field.name}": ({parts}),')
            lines.append("    }")
        enums = self.namer.enum_fields(record)
        if enums:
            lines.append("    _yace_enums = {")
            for name, pyenum in enums.items():
                lines.append(f'        "{name}": {pyenum},')
            lines.append("    }")
        args = ", ".join(f"{self.attr(f.name, record)}=None" for f in fields)
        this = self.this(record)
        lines += [
            "",
            f"    cdef {ctype} *_yace_p",
            f"    cdef {ctype} _yace_c",
            "",
            "    def __cinit__(self, *args, **kwargs):",
            "        memset(&self._yace_c, 0, sizeof(self._yace_c))",
            "        self._yace_p = &self._yace_c",
            "        self._yace_vp = self._yace_p",
            "",
            f"    def __init__({this}, {args}):" if args else "    def __init__(self):",
        ]
        for field in fields:
            attr = self.attr(field.name, record)
            lines += [
                f"        if {attr} is not None:",
                f"            {this}.{attr} = {attr}",
            ]
        if not fields:
            lines.append("        pass")
        lines += [
            "",
            "    @staticmethod",
            f"    cdef {cls} _view({ctype} *ptr, object owner):",
            f"        cdef {cls} made = {cls}.__new__({cls})",
            "        made._yace_p = ptr",
            "        made._yace_vp = ptr",
            "        made._yace_owner = owner",
            "        return made",
            "",
            "    @staticmethod",
            f"    cdef {cls} _copy({ctype} value):",
            f"        cdef {cls} made = {cls}.__new__({cls})",
            "        made._yace_c = value",
            "        return made",
        ]
        for field in fields:
            lines += properties[field.name] or []
        for field in named:
            if properties[field.name] is None:
                lines += [
                    "",
                    f"    # {field.name} is not bound: the module has no type of it",
                ]
        for field in fields:
            for mask in field.masks:
                name = pygen.accessor(field, mask)
                value = f"self.{self.attr(field.name, record)}"
                doc = pygen.docstring(mask.doc, "        ") or mask.name
                doc = pygen.quoted(doc, "        ")
                lines += [
                    "",
                    "    @property",
                    f"    def {name}(self):",
                    f"        {doc}",
                    "",
                    f"        return ({value} & {mask.value:#x}) >> {mask.lo}",
                    "",
                    f"    @{name}.setter",
                    f"    def {name}(self, value):",
                    f"        if not 0 <= value <= {mask.largest:#x}:",
                    f'            raise ValueError(f"{name} is {mask.width}'
                    f' bit{"s" if mask.width > 1 else ""}, not {{value}}")',
                    f"        {value} = ({value} & ~{mask.value:#x})"
                    f" | (value << {mask.lo})",
                ]
        return "\n".join(lines)

    def flexible(self, field) -> bool:
        return isinstance(field.typ, types.Array) and field.typ.length is None

    def render(self) -> Dict[str, object]:
        self.classes = [
            name for name in self.idioms.handles if any(self.idioms.of(name).values())
        ]
        records = [self.record(r) for r in self.records.values()]
        handles = [self.handle(name) for name in self.classes]
        functions = []
        for call in self.idioms.calls:
            if call.kind == "constructor" and self.usable(call):
                functions.append(self.function(call))
        functions += [self.function(c) for c in self.idioms.functions()]
        # The message of an OSError comes from the library function that the
        # meta names, else from os.strerror()
        errmsg = self.model.errmsg()
        message = f"_str_out({self.names.of(errmsg.name)}())" if errmsg else None
        return {
            "records": records,
            "handles": handles,
            "functions": functions,
            "trampolines": [code for _, code in self.trampolines.values()],
            "errmsg": message,
        }


def bind(defined: str, name: str) -> str:
    """Return the code that binds the function defined as 'defined' to 'name'
    in the module's globals. The function cannot be defined as 'name', because
    'name' is declared by the .pxd, a builtin, or reserved by Cython."""

    return "\n".join(
        [
            f'{defined}.__name__ = {defined}.__qualname__ = "{name}"',
            f'globals()["{name}"] = {defined}',
            f'del globals()["{defined}"]',
        ]
    )
