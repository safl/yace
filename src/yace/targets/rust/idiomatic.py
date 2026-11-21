# SPDX-FileCopyrightText: Simon A. F. Lund <os@safl.dk>
#
# SPDX-License-Identifier: GPL-2.0-only

"""
The idiomatic Rust layer of the crate, the module ``safe``, over the raw
functions: handles that release themselves when dropped, ``io::Result`` for
errors, what is written through ``[out]`` pointers returned, slices for arrays,
``&CStr`` for strings, ``Option`` where NULL is allowed, and closures for
callbacks. See :py:mod:`yace.targets.idiom` for what is derived from where.

A function of the layer is safe where its types check everything the caller
gives: a valid handle, a pointer that is not NULL, a buffer as long as its count,
by the semantics the header documents. One taking a raw pointer, or a record
holding one, is ``unsafe``, as is one returning a string borrowed from one of
several arguments.
"""

import re
from functools import cached_property
from typing import List, Optional

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

from . import rgen

# What a body names unqualified, besides trampolines, or a parameter cannot bind
BOUND = {"ret", "Some", "None", "Ok", "Err"} | rgen.NOT_RAW


# Types the module 'safe' names without a path, from std::ffi and the prelude
STD = {
    "Any",
    "Box",
    "CStr",
    "CString",
    "Drop",
    "Err",
    "Fn",
    "FnMut",
    "FnOnce",
    "NonNull",
    "None",
    "Ok",
    "Option",
    "OsStr",
    "OsString",
    "Result",
    "Send",
    "Sized",
    "Some",
    "String",
    "Sync",
    "Vec",
}


# The lifetime of the buffers the caller gives for [out] arrays, and of the part
# of each that the function returns
BUFFER = "'buf"

# The local of what a partial call returns, whether it fails or not; no
# parameter is named so, as pname() renames one ending in '_'
PARTIAL_VALUE = "value_"

PARTIAL = [
    "/// The error of a call that wrote its outputs before it failed",
    "#[derive(Debug)]",
    "pub struct Partial<T> {",
    "    /// The error the call failed with",
    "    pub error: io::Error,",
    "    /// What the call returns when it succeeds, with what it wrote",
    "    pub value: T,",
    "}",
    "",
    "impl<T> std::fmt::Display for Partial<T> {",
    "    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {",
    "        self.error.fmt(f)",
    "    }",
    "}",
    "",
    "impl<T: std::fmt::Debug> std::error::Error for Partial<T> {",
    "    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {",
    "        Some(&self.error)",
    "    }",
    "}",
    "",
    "impl<T> From<Partial<T>> for io::Error {",
    "    fn from(partial: Partial<T>) -> io::Error {",
    "        partial.error",
    "    }",
    "}",
]


# The lifetime of what a Buffer or a Registration borrows: the handles it was
# made with, and the memory registered
HELD = "'a"

BUFFER_STRUCT = """\
/// Memory the library allocated, freed when dropped with the arguments it
/// was allocated with. It borrows the handles it was allocated with, so they
/// outlive it. The memory may be a device's, such as a GPU's, which the CPU
/// cannot read, and nothing in the API says which; hence the slices of it are
/// unsafe.
pub struct Buffer<'a> {
    ptr: NonNull<c_void>,
    len: usize,
    free: Box<dyn Fn(*mut c_void) + 'a>,
    realloc: Option<Box<dyn Fn(*mut c_void, usize) -> *mut c_void + 'a>>,
}

impl<'a> Buffer<'a> {
    /// The address of the memory
    pub fn as_ptr(&self) -> *mut c_void {
        self.ptr.as_ptr()
    }

    /// The size of the memory in bytes
    pub fn len(&self) -> usize {
        self.len
    }

    /// Whether the memory has no bytes
    pub fn is_empty(&self) -> bool {
        self.len == 0
    }

    /// The memory as bytes
    ///
    /// # Safety
    ///
    /// The memory must be the host's, not a device's.
    pub unsafe fn as_slice(&self) -> &[u8] {
        std::slice::from_raw_parts(self.ptr.as_ptr() as *const u8, self.len)
    }

    /// The memory as bytes, for writing
    ///
    /// # Safety
    ///
    /// The memory must be the host's, not a device's.
    pub unsafe fn as_mut_slice(&mut self) -> &mut [u8] {
        std::slice::from_raw_parts_mut(self.ptr.as_ptr() as *mut u8, self.len)
    }

    /// Resize the memory to 'nbytes', keeping its bytes up to the smaller
    /// size. Where the library cannot resize it, the memory is unchanged.
    pub fn realloc(&mut self, nbytes: usize) -> io::Result<()> {
        let realloc = self
            .realloc
            .as_ref()
            .ok_or_else(|| io::Error::from(io::ErrorKind::Unsupported))?;
        self.ptr = NonNull::new(realloc(self.ptr.as_ptr(), nbytes))
            .ok_or_else(|| io::Error::from(io::ErrorKind::OutOfMemory))?;
        self.len = nbytes;
        Ok(())
    }
}

impl Drop for Buffer<'_> {
    fn drop(&mut self) {
        (self.free)(self.ptr.as_ptr());
    }
}"""

REGISTRATION_STRUCT = """\
/// Memory of the caller's that the library uses until it is unregistered,
/// when dropped or by unregister(). It borrows the memory, and the handles it
/// was registered with, so they outlive it.
pub struct Registration<'a> {
    memory: &'a mut [u8],
    unregister: Option<Box<dyn Fn(*mut c_void) -> io::Result<()> + 'a>>,
}

impl Registration<'_> {
    /// Unregister the memory, with the error that unregistering fails with
    pub fn unregister(mut self) -> io::Result<()> {
        match self.unregister.take() {
            Some(unregister) => unregister(self.memory.as_mut_ptr() as *mut c_void),
            None => Ok(()),
        }
    }
}

impl std::ops::Deref for Registration<'_> {
    type Target = [u8];

    fn deref(&self) -> &[u8] {
        self.memory
    }
}

impl std::ops::DerefMut for Registration<'_> {
    fn deref_mut(&mut self) -> &mut [u8] {
        self.memory
    }
}

impl Drop for Registration<'_> {
    fn drop(&mut self) {
        if let Some(unregister) = self.unregister.take() {
            let _ = unregister(self.memory.as_mut_ptr() as *mut c_void);
        }
    }
}"""


class Renderer(object):
    def __init__(self, idioms: Idioms, namer: rgen.Namer):
        self.idioms = idioms
        self.namer = namer
        self.model = idioms.model

    @cached_property
    def reserved(self) -> set:
        """What a body names unqualified, or a parameter cannot bind: the
        types the module imports from the crate, as an enum's newtype is a tuple
        struct, which a binding may not shadow"""

        return BOUND | set(self.namer.names.values())

    def pname(self, name: str) -> str:
        """A parameter's name in Rust, other than a name the body uses, such as
        the local 'ret', a trampoline or a type; one ending in '_' gets
        another '_' appended, so no two parameters share a name"""

        if name in self.reserved or name.endswith(("_", "_trampoline")):
            return f"{name}_"
        return rgen.ident(name)

    def local(self, call: Call, param: str, suffix: str) -> str:
        """The local made for 'param', other than the name of a parameter"""

        return local(
            self.pname(param), suffix, {self.pname(a.param) for a in call.args}
        )

    def alias(self, typedef: str, suffix: str) -> str:
        """The name of a closure type of the callback 'typedef', other than that
        of any raw type, which the module 'safe' imports"""

        name = f"{camel(typedef)}{suffix}"
        structs = {self.struct_name(h) for h in self.idioms.handles}
        while (
            name in self.namer.names.values()
            or name in self.namer.stubs.values()
            or name in structs
        ):
            name += "Closure"
        return name

    def struct_name(self, handle: str) -> str:
        """The name of a handle's struct, other than that of any raw type and
        of any the module uses from std and the prelude"""

        name = camel(self.idioms.handle_name(handle))
        if (
            name in self.namer.names.values()
            or name in self.namer.stubs.values()
            or name in STD
        ):
            name += "Handle"
        return rgen.ident(name)

    def raw(self, typ, param=False) -> str:
        """The raw type, named from inside the module 'safe'"""

        return self.namer.rtype(typ, param)

    def callback_typedef(self, typ) -> Optional[str]:
        """The name of the callback typedef 'typ' refers to, if it does"""

        if isinstance(typ, types.TypedefRef) and typ.name in self.namer.typedefs:
            resolved = self.namer.resolve(typ)
            if isinstance(resolved, types.Pointer) and isinstance(
                resolved.to, types.FunctionType
            ):
                return typ.name
        return None

    def closure_param(self, typ) -> str:
        if isinstance(typ, types.Pointer) and isinstance(typ.to, types.Record):
            mut = "" if typ.to.const else "mut "
            return f"&{mut}{self.raw(typ.to)}"
        return self.raw(typ, True)

    def closure_type(self, name: str, kind: str = "FnMut") -> str:
        func = self.namer.resolve(self.model.find(name, decls.Typedef).typ).to
        params = [
            self.closure_param(p.typ) for p in func.params if not is_void_ptr(p.typ)
        ]
        return f"dyn {kind}({', '.join(params)}){self.namer.ret(func.ret)}"

    def trampolines(self, name: str, lifetimes: set) -> str:
        """The closure types of the callback typedef 'name', and a trampoline
        for each lifetime: a borrowed closure, one boxed and called once, or one
        boxed and kept by the handle"""

        func = self.namer.resolve(self.model.find(name, decls.Typedef).typ).to
        params, passed, ctx = [], [], None
        for i, param in enumerate(func.params):
            pname = f"a{i}"
            params.append(f"{pname}: {self.raw(param.typ, True)}")
            if is_void_ptr(param.typ):
                ctx = pname
            elif isinstance(param.typ, types.Pointer) and isinstance(
                param.typ.to, types.Record
            ):
                passed.append(f"&{'' if param.typ.to.const else 'mut '}*{pname}")
            else:
                passed.append(pname)
        alias = self.alias(name, "Fn")
        once = self.alias(name, "Once")
        sent = self.alias(name, "OnceSend")
        head = f"({', '.join(params)}){self.namer.ret(func.ret)} {{"
        call = f"    f({', '.join(passed)})"
        lines = [
            f"/// The closures given as {self.namer(name)}",
            f"pub type {alias}<'a> = {self.closure_type(name)} + 'a;",
        ]
        if "once" in lifetimes:
            lines += [
                "",
                f"/// The closures given as {self.namer(name)}, called once",
                f"pub type {once} = {self.closure_type(name, 'FnOnce')} + 'static;",
            ]
        if "once-send" in lifetimes:
            lines += [
                "",
                f"/// The closures given as {self.namer(name)}, called once, from",
                "/// whichever thread calls into the library next",
                f"pub type {sent} = {self.closure_type(name, 'FnOnce')}"
                " + Send + 'static;",
            ]
        if "call" in lifetimes:
            lines += [
                "",
                f'unsafe extern "C" fn {name}_trampoline{head}',
                f"    let f = &mut **({ctx} as *mut &mut {alias});",
                call,
                "}",
            ]
        if "once" in lifetimes:
            lines += [
                "",
                f'unsafe extern "C" fn {name}_once_trampoline{head}',
                f"    let f = Box::from_raw({ctx} as *mut Box<{once}>);",
                call,
                "}",
            ]
        if "handle" in lifetimes:
            lines += [
                "",
                f'unsafe extern "C" fn {name}_handle_trampoline{head}',
                f"    let f = &mut **({ctx} as *mut Box<{alias}<'static>>);",
                call,
                "}",
            ]
        return "\n".join(lines)

    def raw_callback(self, call: Call, arg: Arg) -> bool:
        """Whether the context 'arg' is of a callback declared inline, which has
        no trampoline, so both are given raw"""

        owner = next(a for a in call.args if a.param == arg.of)
        return self.callback_typedef(owner.typ) is None

    def param_type(self, call: Call, arg: Arg) -> Optional[str]:
        """The Rust type of a parameter given by the caller, None when hidden"""

        typ = arg.typ
        opt = (lambda t: f"Option<{t}>") if arg.nullable else (lambda t: t)
        if self.makes(call) == "register" and arg.param == call.memory.ptr:
            return f"&{HELD} mut [u8]"
        if self.makes(call) == "register" and arg.param == call.memory.nbytes:
            return None  # the length of the slice
        if arg.kind == "context" and self.raw_callback(call, arg):
            return self.raw(typ, True)
        if arg.kind == "string":
            return opt("&str" if call.counted(arg) else "&CStr")
        if arg.kind == "sequence":
            mut = "" if getattr(typ.to, "const", False) else "mut "
            return opt(f"&{mut}[{self.elem(typ.to)}]")
        if arg.kind == "callback":
            name = self.callback_typedef(typ)
            if name is None:
                return self.raw(typ, True)
            if arg.lifetime == "once":
                once = "OnceSend" if self.sent(call, arg) else "Once"
                return opt(f"Box<{self.alias(name, once)}>")
            if arg.lifetime == "handle":
                return opt(f"Box<{self.alias(name, 'Fn')}<'static>>")
            return opt(f"&mut {self.alias(name, 'Fn')}")
        if arg.kind == "out" and call.out(arg.param).kind == "array":
            return f"&{BUFFER} mut [{self.elem(call.out(arg.param).typ)}]"
        if arg.kind != "value":
            return None
        handle = is_opaque_ptr(typ, self.idioms.handles)
        if handle and any(self.idioms.of(handle).values()):
            return opt(f"&{self.struct_name(handle)}")
        if isinstance(typ, types.Pointer) and not is_void_ptr(typ):
            if isinstance(typ.to, (types.Record, types.Builtin)):
                mut = "" if typ.to.const else "mut "
                return opt(f"&{mut}{self.raw(typ.to)}")
        return self.raw(typ, True)

    def param_expr(self, call: Call, arg: Arg) -> str:
        """The expression passing the parameter on to the raw function"""

        name = self.pname(arg.param)
        typ = arg.typ
        if self.makes(call) == "register" and arg.param == call.memory.ptr:
            return f"{name}.as_mut_ptr() as *mut c_void"
        if self.makes(call) == "register" and arg.param == call.memory.nbytes:
            ptr = self.pname(call.memory.ptr)
            return f"{ptr}.len() as {self.raw(typ)}"
        if arg.kind == "self":
            return "self.ptr.as_ptr()"
        if arg.kind == "string":
            ptr = "s.as_ptr() as *const c_char" if call.counted(arg) else "s.as_ptr()"
            if arg.nullable:
                return f"{name}.map_or(std::ptr::null(), |s| {ptr})"
            return ptr.replace("s.", f"{name}.", 1)
        if arg.kind == "sequence":
            mut = "" if getattr(typ.to, "const", False) else "_mut"
            ptr = f"s.as{mut}_ptr()"
            if is_void_ptr(typ):
                ptr += f" as *{'const' if not mut else 'mut'} c_void"
            if arg.nullable:
                return f"{name}.map_or(std::ptr::null{mut}(), |s| {ptr})"
            return ptr.replace("s.", f"{name}.", 1)
        if arg.kind == "length":
            return f"{self.size(call, arg.of)} as {self.raw(typ)}"
        if arg.kind == "capacity":
            return f"{self.size(call, arg.of)} as {self.raw(typ)}"
        if arg.kind == "size":
            record = self.raw(call.sized(arg))
            return f"core::mem::size_of::<{record}>() as {self.raw(typ)}"
        if arg.kind == "count":
            return f"&mut {name}"
        if arg.kind == "out":
            out = next(o for o in call.outs if o.param == arg.param)
            if out.kind == "array" and is_void_ptr(arg.typ):
                return f"{name}.as_mut_ptr() as *mut c_void"
            if out.kind == "array":
                return f"{name}.as_mut_ptr()"
            return f"&mut {name}"
        if arg.kind == "callback":
            if self.callback_typedef(typ) is None:
                return name
            return self.local(call, arg.param, "cb")
        if arg.kind == "context" and self.raw_callback(call, arg):
            return self.pname(arg.param)
        if arg.kind == "context":
            return self.local(call, arg.of, "ctx")
        handle = is_opaque_ptr(typ, self.idioms.handles)
        if arg.kind == "value" and handle and any(self.idioms.of(handle).values()):
            if arg.nullable:
                return f"{name}.map_or(std::ptr::null_mut(), |h| h.as_ptr())"
            return f"{name}.as_ptr()"
        if self.param_type(call, arg) != self.raw(typ, True) and arg.nullable:
            ptr = "*const _" if typ.to.const else "*mut _"
            mut = "" if typ.to.const else "_mut"
            return f"{name}.map_or(std::ptr::null{mut}(), |r| r as {ptr})"
        return name

    def length(self, call: Call, out) -> str:
        """The local of the number of elements of the [out] array 'out' that the
        function wrote, at most the length of the buffer"""

        return self.local(call, out.param, "len")

    def lengths(self, call: Call) -> List[str]:
        """The statements setting each local of length(), after the call"""

        found = []
        count = "ret as usize" if call.returns == "count" else None
        for out in call.outs:
            if out.kind != "array":
                continue
            written = f"{self.pname(out.count)} as usize" if out.count else count
            if not out.count:
                count = None
            if written:
                name = self.pname(out.param)
                found.append(
                    f"let {self.length(call, out)} = ({written}).min({name}.len());"
                )
        return found

    def results(self, call: Call):
        """The (type, expression) of each value the function returns"""

        if self.makes(call) == "register":
            made = f"{self.registration_struct}<{HELD}>"
            return [(made, self.local(call, "registration", "made"))]
        found = []
        count = "ret" if call.returns == "count" else None
        for out in call.outs:
            name = self.pname(out.param)
            if out.kind == "array":
                typ = f"&{BUFFER} mut [{self.elem(out.typ)}]"
                written = out.count or count
                if not out.count:
                    count = None  # the count is that of the array, not returned too
                if written:
                    found.append((typ, f"&mut {name}[..{self.length(call, out)}]"))
                else:
                    found.append((typ, name))
            elif out.kind == "handle":
                struct = self.struct_name(out.typ.to.name)
                found.append((struct if call.errno else f"Option<{struct}>", name))
            else:
                found.append((self.raw(out.typ), name))
        if count:
            found.append(("usize", "ret as usize"))

        opt = (lambda t: f"Option<{t}>") if call.nullable else (lambda t: t)
        ret = call.ret
        if self.makes(call) == "alloc":
            made = f"{self.buffer_struct}<{HELD}>"
            made = f"Option<{made}>" if call.nullable else made
            found.append((made, self.local(call, "buffer", "made")))
        elif call.returns == "value":
            found.append((self.raw(ret), "ret"))
        elif call.returns == "string":
            life = (
                "" if call.kind == "method" or self.borrows(call) == 1 else "'static "
            )
            expr = "unsafe { CStr::from_ptr(ret) }"
            if call.nullable:
                expr = f"(!ret.is_null()).then(|| {expr})"
            found.append((opt(f"&{life}CStr"), expr))
        elif (
            call.returns == "pointer"
            and isinstance(ret.to, (types.Record, types.Builtin))
            and not is_void_ptr(ret)
            and copyable(self.model, ret.to)
        ):
            expr = "unsafe { ret.as_ref() }.copied()"
            if not call.nullable:
                expr = "unsafe { *ret }"
            found.append((opt(self.raw(ret.to)), expr))
        elif call.returns in ("pointer", "handle"):
            found.append((self.raw(ret), "ret"))
        return found

    def size(self, call: Call, param: str) -> str:
        """The number of elements of the slice given as 'param'"""

        arg = next(a for a in call.args if a.param == param)
        name = self.pname(param)
        if arg.nullable and arg.kind != "out":  # a buffer is always given
            return f"{name}.map_or(0, |s| s.len())"
        return f"{name}.len()"

    def elem(self, typ) -> str:
        """The Rust type of an element of an array, bytes for void"""

        if isinstance(typ, types.Builtin) and typ.name == "void":
            return "u8"
        return self.raw(typ)

    def boxed(self, call: Call, arg: Arg, cb: str) -> List[str]:
        """Statements boxing the closure of a callback the library keeps: for a
        callback of @lifetime once, the trampoline frees the box; else the
        handle keeps it"""

        name = self.pname(arg.param)
        made = self.local(call, arg.param, "cb")
        ctx = self.local(call, arg.param, "ctx")
        if arg.lifetime == "once":
            tramp = f"Some({cb}_once_trampoline as _)"
            boxed = (
                f"f as Box<{self.alias(cb, 'Once')}>" if self.sent(call, arg) else "f"
            )
            into = f"Box::into_raw(Box::new({boxed})) as *mut c_void"
            lines = []
        else:
            tramp = f"Some({cb}_handle_trampoline as _)"
            into = (
                "{ self.keep.push(Box::new(f));"
                " &mut **self.keep.last_mut().unwrap() as *mut dyn std::any::Any"
                " as *mut c_void }"
            )
            kept = self.local(call, arg.param, "kept")
            lines = [f"let {kept} = self.keep.len();"] if call.errno else []
        if arg.nullable:
            return lines + [
                f"let ({made}, {ctx}) = match {name} {{",
                f"    Some(f) => ({tramp}, {into}),",
                "    None => (None, std::ptr::null_mut()),",
                "};",
            ]
        return lines + [
            f"let {made} = {tramp};",
            f"let {ctx} = {{ let f = {name}; {into} }};",
        ]

    @staticmethod
    def sent(call: Call, arg: Arg) -> bool:
        """Whether the closure of the callback 'arg' must be Send: a closure
        given once to a function of no handle may be run by any later call into
        the library, from any thread, where a method's closure runs in a call
        given its handle, which stays on its thread"""

        return arg.lifetime == "once" and call.kind != "method"

    def keeps(self, record: str) -> bool:
        """Whether the handle keeps closures, for its methods to give"""

        return any(
            a.lifetime == "handle" and a.kind == "callback"
            for call in self.idioms.of(record)["method"]
            for a in call.args
            if self.usable(call)
        )

    def has_pointers(self, typ, seen=None) -> bool:
        """Whether a value of 'typ' holds a pointer, which safe Rust can make
        point anywhere"""

        seen = set() if seen is None else seen
        typ = self.namer.resolve(typ)
        if isinstance(typ, (types.Pointer, types.FunctionType, types.TypedefRef)):
            return True
        if isinstance(typ, types.Array):
            return self.has_pointers(typ.of, seen)
        if isinstance(typ, types.Record) and typ.name not in seen:
            seen.add(typ.name)
            record = self.model.find(typ.name, decls.RECORDS)
            return record is None or any(
                self.has_pointers(f.typ, seen) for f in record.fields
            )
        return False

    def borrows(self, call: Call) -> int:
        """How many references the caller gives, besides the handle"""

        return sum(
            "&" in (self.param_type(call, a) or "")
            for a in call.args
            if a.kind not in ("self", "out")
        )

    def unbound_string(self, call: Call) -> bool:
        """Whether a returned string borrows from one of several arguments, which
        the signature cannot say"""

        return (
            call.returns == "string"
            and call.kind != "method"
            and self.borrows(call) > 1
        )

    def is_unsafe(self, call: Call) -> bool:
        """Whether a caller could make the call unsound: by giving a raw
        pointer, or a record holding one, or by using a string past its life"""

        if self.unbound_string(call):
            return True
        for arg in call.args:
            if self.makes(call) == "register" and arg.param == call.memory.ptr:
                continue
            if arg.kind == "value":
                typ = arg.typ
                if isinstance(typ, types.Pointer):
                    if is_void_ptr(typ) or not isinstance(
                        typ.to, (types.Record, types.Builtin)
                    ):
                        return True
                    typ = typ.to
                if self.has_pointers(typ):
                    return True
            elif arg.kind == "sequence" and self.has_pointers(arg.typ.to):
                return True
            elif arg.kind == "callback" and self.callback_typedef(arg.typ) is None:
                return True
        return False

    def function(self, call: Call, indent: str = "") -> List[str]:
        func = self.idioms.decl(call.function)
        params = []
        if call.kind in ("method", "destructor"):
            this = next(a for a in call.args if a.kind == "self")
            if call.kind == "destructor":
                params.append("self")
            else:
                keeps = any(a.lifetime == "handle" for a in call.args)
                params.append(
                    "&self" if this.typ.to.const and not keeps else "&mut self"
                )
        for arg in call.args:
            typ = self.param_type(call, arg)
            if typ is not None and arg.kind != "self":
                params.append(f"{self.pname(arg.param)}: {typ}")

        results = self.results(call)
        if not results:
            rtype, rexpr = "()", "()"
        elif len(results) == 1:
            rtype, rexpr = results[0]
        else:
            rtype = f"({', '.join(t for t, _ in results)})"
            rexpr = f"({', '.join(e for _, e in results)})"
        value = rexpr
        if call.partial:
            rtype, rexpr = f"Result<{rtype}, Partial<{rtype}>>", f"Ok({rexpr})"
        elif call.errno:
            rtype, rexpr = f"io::Result<{rtype}>", f"Ok({rexpr})"
        uses_ret = call.errno or call.returns != "nothing"

        body: List[str] = []
        for arg in call.args:
            if arg.kind in ("length", "capacity"):
                count = self.size(call, arg.of)
                for other in arg.shared:
                    body.append(
                        f"assert_eq!({self.size(call, other)}, {count},"
                        f" \"'{other}' does not have the count '{arg.param}'\");"
                    )
        for arg in call.args:
            name = self.pname(arg.param)
            if arg.kind == "count":
                body.append(f"let mut {name}: {self.raw(arg.typ.to)} = 0;")
            elif arg.kind == "out":
                out = next(o for o in call.outs if o.param == arg.param)
                if out.kind == "array":
                    continue  # the caller's buffer
                elif out.kind == "handle":
                    body.append(f"let mut {name} = std::ptr::null_mut();")
                elif isinstance(out.typ, types.Pointer):
                    body.append(
                        f"let mut {name}: {self.raw(out.typ)} = std::ptr::null_mut();"
                    )
                else:
                    body.append(f"let mut {name} = {self.raw(out.typ)}::default();")
            elif arg.kind == "callback" and self.callback_typedef(arg.typ):
                cb = self.callback_typedef(arg.typ)
                if arg.lifetime in ("once", "handle"):
                    body += self.boxed(call, arg, cb)
                    continue
                tramp = f"Some({cb}_trampoline as _)"
                made = self.local(call, arg.param, "cb")
                ctx = self.local(call, arg.param, "ctx")
                if arg.nullable:
                    body += [
                        f"let mut {name} = {name};",
                        f"let ({made}, {ctx}) = match {name}.as_mut() {{",
                        f"    Some(f) => ({tramp}, f as *mut _ as *mut c_void),",
                        "    None => (None, std::ptr::null_mut()),",
                        "};",
                    ]
                else:
                    body += [
                        f"let mut {name} = {name};",
                        f"let {made} = {tramp};",
                        f"let {ctx} = &mut {name} as *mut _ as *mut c_void;",
                    ]

        args = ", ".join(self.param_expr(call, a) for a in call.args)
        raw_call = f"unsafe {{ super::{rgen.ident(call.function)}({args}) }};"
        body.append(f"let ret = {raw_call}" if uses_ret else raw_call)
        failed: List[str] = []  # what an error releases, and how it returns
        if call.errno:
            for arg in call.args:
                if arg.kind == "callback" and self.callback_typedef(arg.typ) is None:
                    continue
                if arg.kind == "callback" and arg.lifetime == "once":
                    ctx = self.local(call, arg.param, "ctx")
                    once = self.alias(self.callback_typedef(arg.typ), "Once")
                    failed += [
                        f"    if !{ctx}.is_null() {{",
                        f"        let f = {ctx} as *mut Box<{once}>;",
                        "        std::mem::drop(unsafe { Box::from_raw(f) });",
                        "    }",
                    ]
                elif arg.kind == "callback" and arg.lifetime == "handle":
                    kept = self.local(call, arg.param, "kept")
                    failed.append(f"    self.keep.truncate({kept});")
            error = "io::Error::from_raw_os_error(-(ret as i32))"
            if call.partial:
                error = f"Partial {{ error: {error}, value: {PARTIAL_VALUE} }}"
            failed = ["if ret < 0 {"] + failed + [f"    return Err({error});", "}"]
        body += self.lengths(call)
        if not call.partial:
            body += failed
        for out in call.outs:
            name = self.pname(out.param)
            if out.kind == "handle" and not call.errno:
                struct = self.struct_name(out.typ.to.name)
                keep = ", keep: Vec::new()" if self.keeps(out.typ.to.name) else ""
                made = f"{struct} {{ ptr{keep} }}"
                body.append(f"let {name} = NonNull::new({name}).map(|ptr| {made});")
            elif out.kind == "handle":
                struct = self.struct_name(out.typ.to.name)
                body += [
                    f"let {name} = {struct} {{",
                    f"    ptr: NonNull::new({name}).ok_or_else(|| {{",
                    f'        io::Error::other("{call.function}() gave no handle")',
                    "    })?,",
                ]
                if self.keeps(out.typ.to.name):
                    body.append("    keep: Vec::new(),")
                body.append("};")
        if call.partial:
            body.append(f"let {PARTIAL_VALUE} = {value};")
            body += failed
            rexpr = f"Ok({PARTIAL_VALUE})"
        if call.kind == "destructor" and self.keeps(call.handle):
            body.append("std::mem::drop(unsafe { std::ptr::read(&self.keep) });")
        if call.kind == "destructor":
            body.insert(0, "let mut this = std::mem::ManuallyDrop::new(self);")
            body = [line.replace("self.", "this.") for line in body]
        if self.makes(call):
            body += self.made(call)
            params = [self.held(p) for p in params]
        if rexpr != "()":
            body.append(rexpr)

        shown, errors = call_doc(
            call,
            func.doc,
            self.pname,
            "The error is a [`Partial`], whose `value` is what the call returns"
            " when it succeeds, with what was written before it failed.",
            buffers=True,
        )
        if self.makes(call) == "register":
            params_doc = dict(shown.params)
            params_doc.pop(self.pname(call.memory.nbytes), None)
            shown = shown.model_copy(update={"params": params_doc})
        calls = f"Calls [`super::{rgen.ident(call.function)}`]."
        lines = [
            f"/// {line}".rstrip() for line in rgen.doc_lines(shown, errors, [calls])
        ]
        name = rgen.ident(call.name)
        if call.name == "as_ptr" and call.kind != "function":
            name = "as_ptr_"
        if self.is_unsafe(call):
            lines += ["///", "/// # Safety", "///"]
            if self.unbound_string(call):
                lines += [
                    "/// The string returned must not be used longer than",
                    f"/// {call.function}() allows; nothing here ties it to an",
                    "/// argument.",
                ]
            else:
                lines += [
                    "/// Pointers given, also those in records, must be valid for",
                    f"/// {call.function}(); nothing here can check them.",
                ]
        unsafe = "unsafe " if self.is_unsafe(call) else ""
        arrow = "" if rtype == "()" else f" -> {rtype}"
        lifetimes = [HELD] if self.makes(call) else []
        if any(o.kind == "array" for o in call.outs):
            lifetimes.append(BUFFER)
        generic = f"<{', '.join(lifetimes)}>" if lifetimes else ""
        lines.append(f"pub {unsafe}fn {name}{generic}({', '.join(params)}){arrow} {{")
        lines += [f"    {line}" for line in body]
        lines.append("}")
        return [f"{indent}{line}".rstrip() for line in lines]

    def again(self, call: Call, partner: Optional[Call]) -> Optional[List[str]]:
        """The expressions of the arguments of 'partner', computed from those
        of 'call', with 'p' as the address and 'n' as the new size; None where
        'partner' takes what 'call' has no value of that a closure can keep"""

        if partner is None or partner.memory is None:
            return None
        given = {a.param: a for a in call.args}
        found = []
        for param in self.idioms.decl(partner.function).params:
            arg = given.get(param.name)
            if param.name == partner.memory.ptr:
                found.append("p")
            elif param.name == partner.memory.nbytes:
                found.append(f"n as {self.raw(param.typ)}")
            elif arg is not None and arg.kind == "self":
                found.append("self.ptr.as_ptr()")
            elif arg is not None and arg.kind == "value":
                typ = self.param_type(call, arg) or ""
                handle = is_opaque_ptr(arg.typ, self.idioms.handles)
                if "&" in typ and not handle:
                    return None  # a reference, which two closures cannot share
                found.append(self.param_expr(call, arg))
            else:
                return None
        return found

    def makes(self, call: Call) -> Optional[str]:
        """'alloc' where 'call' returns a Buffer, 'register' where it returns a
        Registration: where the struct can release what 'call' made"""

        if call.memory is None or call.memory.role not in ("alloc", "register"):
            return None
        role = "free" if call.memory.role == "alloc" else "unregister"
        if self.again(call, self.idioms.partner(call, role)) is None:
            return None
        return call.memory.role

    def bound(self, call: Call) -> bool:
        """Whether 'call' is bound by a name of its own, not only through the
        struct of the buffer pattern that calls it"""

        if call.memory is None or call.memory.role not in RELEASES:
            return True
        owner = self.idioms.owner(call)
        return owner is None or not self.makes(owner)

    def held(self, param: str) -> str:
        """The parameter 'param' with its references of the lifetime HELD. The
        handle is borrowed shared, so that it can make several buffers or
        registrations, each holding the borrow."""

        if param in ("&self", "&mut self"):
            return f"&{HELD} self"
        name, typ = param.split(": ", 1)
        if typ.startswith(("&", "Option<&")) and "'" not in typ.split("[")[0]:
            typ = typ.replace("&", f"&{HELD} ", 1)
        return f"{name}: {typ}"

    def closure(self, call: Call, role: str) -> Optional[str]:
        """The Box of a closure calling the partner of the role 'role' with the
        arguments 'call' was given, None where there is no such partner"""

        partner = self.idioms.partner(call, role)
        args = self.again(call, partner)
        if partner is None or args is None:
            return None
        lets = []
        for i, expr in enumerate(args):
            if expr != "p" and not expr.startswith("n as "):
                lets.append(f"let a{i} = {expr};")
                args[i] = f"a{i}"
        raw = f"super::{rgen.ident(partner.function)}({', '.join(args)})"
        if role == "realloc":
            fn = f"move |p, n| unsafe {{ {raw} }}"
        elif role == "unregister" and partner.errno:
            fn = (
                f"move |p| match unsafe {{ {raw} }} {{"
                " ret if ret < 0 => Err(io::Error::from_raw_os_error(-(ret as i32))),"
                " _ => Ok(()) }"
            )
        elif role == "unregister":
            fn = f"move |p| {{ unsafe {{ {raw} }}; Ok(()) }}"
        else:
            fn = f"move |p| {{ unsafe {{ {raw} }}; }}"
        return f"{{ {' '.join(lets)} Box::new({fn}) }}".replace("{  Box", "{ Box")

    def made(self, call: Call) -> List[str]:
        """The statements making the Buffer or the Registration of 'call'"""

        if self.makes(call) == "register":
            made = self.local(call, "registration", "made")
            unregister = self.closure(call, "unregister")
            return [
                f"let {made} = {self.registration_struct} {{",
                f"    memory: {self.pname(call.memory.ptr)},",
                f"    unregister: Some({unregister}),",
                "};",
            ]
        made = self.local(call, "buffer", "made")
        realloc = self.closure(call, "realloc")
        fields = [
            f"    len: {self.pname(call.memory.nbytes)},",
            f"    free: {self.closure(call, 'free')},",
            f"    realloc: {f'Some({realloc})' if realloc else 'None'},",
        ]
        if call.nullable:
            return (
                [f"let {made} = NonNull::new(ret).map(|ptr| {self.buffer_struct} {{"]
                + ["    ptr,"]
                + fields
                + ["});"]
            )
        return (
            [
                f"let {made} = {self.buffer_struct} {{",
                f'    ptr: NonNull::new(ret).expect("{call.function}() gave NULL"),',
            ]
            + fields
            + ["};"]
        )

    def taken(self, name: str) -> bool:
        structs = {self.struct_name(h) for h in self.idioms.handles}
        return (
            name in self.namer.names.values()
            or name in self.namer.stubs.values()
            or name in structs
            or name in STD
        )

    @cached_property
    def buffer_struct(self) -> str:
        """Buffer, or Buffer_ where a type of the crate or a handle is Buffer"""

        return "Buffer_" if self.taken("Buffer") else "Buffer"

    @cached_property
    def registration_struct(self) -> str:
        """Registration, or Registration_ where a type of the crate or a handle
        is Registration"""

        return "Registration_" if self.taken("Registration") else "Registration"

    def usable(self, call: Call) -> bool:
        for out in call.outs:
            if out.kind == "record":
                record = self.model.find(out.typ.name, decls.RECORDS)
                if record is None or not record.fields:
                    return False  # no fields to make the record of
        return True

    def handle(self, record: str) -> List[str]:
        calls = self.idioms.of(record)
        struct = self.struct_name(record)
        raw = self.namer(record)
        entity = self.model.find(record, decls.RECORDS)
        destructor = calls["destructor"][0] if calls["destructor"] else None
        lines = [f"/// {line}".rstrip() for line in rgen.doc_lines(entity.doc)]
        lines += [
            "///",
            f"/// Owns a [`super::{raw}`]"
            + (
                f", released when dropped, by [`super::{destructor.function}`]."
                if destructor
                else "; nothing releases it."
            ),
            f"pub struct {struct} {{",
            f"    ptr: NonNull<super::{raw}>,",
        ]
        if self.keeps(record):
            lines.append("    keep: Vec<Box<dyn std::any::Any>>,")
        lines += [
            "}",
            "",
            f"impl {struct} {{",
            f"    /// The raw pointer, still owned by the {struct}",
            f"    pub fn as_ptr(&self) -> *mut super::{raw} {{",
            "        self.ptr.as_ptr()",
            "    }",
        ]
        for call in calls["constructor"] + calls["method"]:
            if self.usable(call) and self.bound(call):
                lines += [""] + self.function(call, "    ")
        if destructor:
            lines += [""] + self.function(destructor, "    ")
        lines.append("}")
        if destructor:
            destroy = (
                f"unsafe {{ super::{rgen.ident(destructor.function)}"
                "(self.ptr.as_ptr()) }"
            )
            lines += ["", f"impl Drop for {struct} {{", "    fn drop(&mut self) {"]
            if destructor.errno and self.keeps(record):
                lines += [
                    f"        if {destroy} < 0 {{",
                    "            std::mem::forget(std::mem::take(&mut self.keep));",
                    "        }",
                ]
            else:
                lines.append(f"        {destroy};")
            lines += ["    }", "}"]
        elif self.keeps(record):
            lines += [
                "",
                f"impl Drop for {struct} {{",
                "    fn drop(&mut self) {",
                "        std::mem::forget(std::mem::take(&mut self.keep));",
                "    }",
                "}",
            ]
        return lines

    def render(self) -> str:
        lines = [
            "/// The idiomatic layer, over the raw functions of the crate",
            "pub mod safe {",
            "    #![allow(unused_imports, unused_mut, clippy::all)]",
            "    use std::ffi::*;",
            "    use std::io;",
            "    use std::ptr::NonNull;",
            "",
        ]
        callbacks: dict = {}
        for call in self.idioms.calls:
            for arg in call.args:
                name = self.callback_typedef(arg.typ)
                if arg.kind == "callback" and name and self.usable(call):
                    callbacks.setdefault(name, set()).add(arg.lifetime)
                    if self.sent(call, arg):
                        callbacks[name].add("once-send")
        for name in sorted(callbacks):
            text = self.trampolines(name, callbacks[name])
            lines += [""] + [f"    {ln}".rstrip() for ln in text.splitlines()]
        for record in self.idioms.handles:
            if any(self.idioms.of(record).values()):
                lines += [""] + [f"    {ln}".rstrip() for ln in self.handle(record)]
        for call in self.idioms.functions():
            if self.usable(call) and self.bound(call):
                lines += [""] + self.function(call, "    ")
        made = {self.makes(c) for c in self.idioms.calls if self.usable(c)}
        for role, text, struct, name in [
            ("alloc", BUFFER_STRUCT, self.buffer_struct, "Buffer"),
            ("register", REGISTRATION_STRUCT, self.registration_struct, "Registration"),
        ]:
            if role in made:
                text = re.sub(rf"\b{name}\b", struct, text)
                lines += [""] + [f"    {ln}".rstrip() for ln in text.splitlines()]
        if any(c.partial and self.usable(c) for c in self.idioms.calls):
            lines += [""] + [f"    {ln}".rstrip() for ln in PARTIAL]
        lines.append("}")
        # The types of the crate, not its constants, which would be read as
        # patterns where a parameter or local is named as one
        named = sorted(set(self.namer.names.values()) | set(self.namer.stubs.values()))
        lines.insert(6, f"    use super::{{{', '.join(named)}}};")
        return "\n".join(lines)
