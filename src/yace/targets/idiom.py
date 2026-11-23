# SPDX-FileCopyrightText: Simon A. F. Lund <os@safl.dk>
#
# SPDX-License-Identifier: GPL-2.0-only

"""
How the functions of an API are called idiomatically, derived from the IR; each
target renders the calls in its own language.

The calls follow from the semantics of the C subset, see
:py:mod:`yace.ir.semantics`:

* An opaque record is a handle, also when named by a typedef of its own name.
  A function that creates a handle through an ``[out]`` pointer is its
  constructor, the function that ``@destroys`` it is its destructor, and the
  functions that take it as their first parameter are its methods.
* What a function writes through an ``[out]`` pointer is returned: a record, a
  value, a handle, or the elements of an array. The number of elements is the
  count written, or else the count returned, or else the capacity. Python
  allocates the array; Rust, C++, Go and Zig take a buffer from the caller,
  whose length is the capacity, and return the part written.
* An array read through a pointer is given as a sequence, and the binding
  passes its ``@arrparam`` length.
* A ``@recparam`` record is given, and the binding passes its size.
* A callback is given as a closure, kept for as long as its ``@lifetime`` says,
  and the binding passes its ``void *`` context. A callback without a
  ``@lifetime`` is given as the raw function pointer, with its context.
* With ``@errno``, a negative return is an error. A function returning ``int``
  returns nothing on success, unless ``@errno count`` says that the ``int`` is
  a count; any other integer is returned. With ``@errno partial``, the error
  carries the values that the call returns on success.
* A returned ``const char *`` is a string, and a ``@nullable`` pointer is the
  null value of the language when NULL. A ``const char *`` written through an
  ``[out]`` pointer is a string or the null value; Go returns the empty string.

The name of a call is the C name without the prefix of the API, and for a
method also without the name of its handle: ``foo_handle_close()`` is the
method ``close`` of ``handle``. A function taking a ``@recparam`` is named
without the suffix ``_sized``.
"""

from collections import Counter
from typing import (
    Any,
    Callable,
    Dict,
    Iterable,
    Iterator,
    List,
    Literal,
    Optional,
    Tuple,
)

from pydantic import BaseModel

from yace.ir import decls, types
from yace.ir.doc import Doc
from yace.ir.model import Model
from yace.ir.semantics import SIZED


def is_lent(ret) -> bool:
    """Whether a returned pointer is to a record the caller may write: an object
    the library keeps or hands over, of which a copy would be another object"""

    return (
        isinstance(ret, types.Pointer)
        and isinstance(ret.to, types.Record)
        and not ret.to.const
    )


# The roles of the functions bound only as methods of the buffer objects
RELEASES = ("free", "realloc", "unregister")


class Arg(BaseModel):
    """How a parameter of the C function is given, when called idiomatically"""

    param: str  # name of the C parameter
    index: int
    kind: Literal[
        "self",  # the handle the method is called on
        "value",  # given as is
        "string",  # a const char *, given as a string
        "sequence",  # an @arrparam and its length, given as a sequence
        "callback",  # a callback, given as a closure
        "length",  # the count of a sequence; not given
        "size",  # the size of a @recparam record; not given
        "context",  # the void * context of a callback; not given
        "capacity",  # the count of an [out] array; given, as how many to get
        "count",  # the [out] count of an [out] array; its length, not returned
        "out",  # written by the function; returned, not given
    ]
    typ: types.Type
    nullable: bool = False
    of: Optional[str] = None  # the param a length, size, context, ... is of
    shared: List[str] = []  # the other sequences a length or capacity is of
    lifetime: Optional[str] = None


class Out(BaseModel):
    """What the idiomatic function returns for an [out] parameter"""

    param: str
    kind: Literal["record", "value", "handle", "array"]
    typ: types.Type  # the type written: the record, value, handle or element
    capacity: Optional[str] = None  # for an array, the parameter of its count
    count: Optional[str] = None  # for an array, the [out] parameter of its length


CallKind = Literal["constructor", "destructor", "method", "function"]
Returns = Literal["nothing", "value", "string", "pointer", "handle", "count"]


class Call(BaseModel):
    """A C function, as called idiomatically"""

    function: str  # the C name
    name: str  # the idiomatic name
    kind: CallKind
    handle: Optional[str] = None  # the C name of the record it belongs to
    args: List[Arg]
    outs: List[Out]
    errno: bool = False
    partial: bool = False  # whether the error carries what is returned
    returns: Returns
    nullable: bool = False  # whether what is returned may be nothing
    ret: types.Type
    memory: Optional[decls.Memory] = None  # what it does with a buffer, if any

    def given(self, buffers: bool = False) -> List[Arg]:
        """The arguments the caller gives; the binding passes or returns the rest.
        With 'buffers', as Rust, C++, Go and Zig take them, the caller gives
        each [out] array, as a buffer, and its capacity is the buffer's length"""

        return [
            a
            for a in self.args
            if (a.kind in GIVEN and not (buffers and a.kind == "capacity"))
            or (buffers and a.kind == "out" and self.out(a.param).kind == "array")
        ]

    def sized(self, arg: Arg) -> types.Type:
        """The type of the record whose size the 'size' argument 'arg' is,
        without its const"""

        typ = next(a.typ for a in self.args if a.param == arg.of)
        # @recparam was checked to name a pointer to a struct
        assert isinstance(typ, types.Pointer)
        return typ.to.model_copy(update={"const": False})

    def counted(self, arg: Arg) -> bool:
        """Whether 'arg' is a string with a length, which C reads as bytes, not
        to a NUL; the binding takes a string that has a length of its own"""

        return arg.kind == "string" and any(
            a.kind == "length" and arg.param in [a.of, *a.shared] for a in self.args
        )

    def out(self, param: str) -> "Out":
        """What the function writes through the [out] parameter 'param'"""

        return next(o for o in self.outs if o.param == param)


GIVEN = ("value", "string", "sequence", "callback", "capacity")


def call_doc(
    call: Call,
    doc: Doc,
    pname: Callable[[str], str],
    partial: str = "",
    buffers: bool = False,
) -> Tuple[Doc, str]:
    """The doc of 'call', and the text of how the call fails. The doc holds the
    parameters the caller gives, by the names 'pname' gives. With @errno, what the C
    function says it returns is the text of how the call fails, as that text describes
    both the value and the error. With @errno partial, the sentence 'partial' is
    appended. With 'buffers', the caller gives the [out] arrays, see Call.given()"""

    params = {
        pname(a.param): doc.params[a.param]
        for a in call.given(buffers)
        if a.param in doc.params
    }
    if not call.errno:
        return doc.model_copy(update={"params": params}), ""
    errors = f"{call.function}() returns: {doc.returns}" if doc.returns else ""
    if call.partial:
        errors = f"{errors.rstrip('.')}. {partial}" if errors else partial
    return doc.model_copy(update={"params": params, "returns": ""}), errors


def is_opaque_ptr(typ, handles) -> Optional[str]:
    if (
        isinstance(typ, types.Pointer)
        and isinstance(typ.to, types.Record)
        and typ.to.name in handles
    ):
        return typ.to.name
    return None


def local(name: str, suffix: str, taken: Iterable[str]) -> str:
    """The name of a local made for the parameter 'name': 'name_suffix', with
    '_' appended while that name is in 'taken', such as by another parameter.
    So long as no suffix is another suffix followed by '_', no two locals
    share a name"""

    found = f"{name}_{suffix}"
    while found in taken:
        found += "_"
    return found


def typedefs_used(node) -> Iterator[str]:
    """The names of the typedefs 'node' refers to, among them those declared
    outside the headers, such as FILE"""

    if isinstance(node, types.TypedefRef):
        yield node.name
    if isinstance(node, BaseModel):
        node = list(vars(node).values())
    if isinstance(node, list):
        for item in node:
            yield from typedefs_used(item)


def copyable(model: Model, typ) -> bool:
    """Whether a copy of a 'typ' holds all of it: not of a record declared but
    not defined, here or in another header, nor of one ending in a flexible
    array, whose elements follow it"""

    if not isinstance(typ, types.Record):
        return True
    record = model.records().get(typ.name)
    if record is None or not record.fields:
        return False
    last = record.fields[-1].typ
    return not (isinstance(last, types.Array) and last.length is None)


def strip(name: str, *prefixes: str) -> str:
    for prefix in prefixes:
        if prefix and name.startswith(prefix + "_") and len(name) > len(prefix) + 1:
            name = name[len(prefix) + 1 :]
    return name


class Idioms(object):
    """The idiomatic calls of the functions of 'model', and its handles"""

    def __init__(self, model: Model):
        self.model = model
        self.prefix = model.meta.prefix
        self.typedefs = model.typedefs()
        self.handles = {
            name: r
            for name, r in model.records().items()
            if not r.fields and r.size is None
        }
        functions = [e for e in model.entities if isinstance(e, decls.Function)]
        self.decls = {f.name: f for f in functions}
        self.calls = [self.call(f) for f in functions if not f.variadic]
        self.distinct({f.name for f in functions})

    def distinct(self, raw: set):
        """Keep the C name for calls whose idiomatic one is shared, within the
        module or a handle, or is the C name of another function; a constructor
        is in the scope of both, as some targets place it in the handle"""

        def scopes(call: Call) -> List[Optional[str]]:
            if call.kind in ("method", "destructor"):
                return [call.handle]
            return [None, call.handle] if call.kind == "constructor" else [None]

        shared = Counter((s, c.name) for c in self.calls for s in scopes(c))
        for call in self.calls:
            clash = None in scopes(call) and call.name in raw - {call.function}
            if any(shared[(s, call.name)] > 1 for s in scopes(call)) or clash:
                call.name = call.function

    def decl(self, function: str) -> decls.Function:
        """The function with the C name 'function'"""

        return self.decls[function]

    def closure(self, param: decls.Param, params: List[decls.Param]) -> bool:
        """Whether a callback is given as a closure: one typedef'd, with a
        @lifetime and its context; any other is given raw"""

        return (
            self.is_callback(param.typ)
            and isinstance(param.typ, types.TypedefRef)
            and param.lifetime is not None
            and any(p.context == param.name for p in params)
        )

    def handle_name(self, record: str) -> str:
        """The name of the handle 'record' without the prefix of the API"""

        return strip(record, self.prefix)

    def resolve(self, typ):
        while isinstance(typ, types.TypedefRef) and typ.name in self.typedefs:
            typ = self.typedefs[typ.name].typ
        return typ

    def is_callback(self, typ) -> bool:
        typ = self.resolve(typ)
        return isinstance(typ, types.Pointer) and isinstance(typ.to, types.FunctionType)

    def call(self, func: decls.Function) -> Call:
        params = func.params
        lengths: Dict[str, List[decls.Param]] = {}  # count -> pointers
        for p in params:
            if p.length:
                lengths.setdefault(p.length, []).append(p)
        counts = {p.count: p.name for p in params if p.count}
        sizes = {p.size: p.name for p in params if p.size}
        bound = {p.name for p in params if self.closure(p, params)}
        contexts = {p.name for p in params if p.context in bound}

        args: List[Arg] = []
        outs: List[Out] = []
        kind: CallKind = "function"
        handle: Optional[str] = None

        for idx, param in enumerate(params):
            typ = param.typ
            pname = param.name or f"arg{idx}"
            arg: Dict[str, Any] = dict(
                param=pname, index=idx, typ=typ, nullable=param.nullable
            )

            if param.name in lengths:
                owners = lengths[param.name]
                outs_of = [p for p in owners if p.direction == "out"]
                owner = outs_of[0] if outs_of else owners[0]
                shared = [p.name for p in owners if p is not owner]
                if outs_of:
                    args.append(
                        Arg(kind="capacity", of=owner.name, shared=shared, **arg)
                    )
                else:
                    args.append(Arg(kind="length", of=owner.name, shared=shared, **arg))
                continue
            if param.name in contexts:
                args.append(Arg(kind="context", of=param.context, **arg))
                continue
            if param.name in counts:
                args.append(Arg(kind="count", of=counts[param.name], **arg))
                continue
            if param.name in sizes:
                args.append(Arg(kind="size", of=sizes[param.name], **arg))
                continue

            if param.direction == "out" and isinstance(typ, types.Pointer):
                made = is_opaque_ptr(typ.to, self.handles)
                if made and not param.length:
                    outs.append(Out(param=pname, kind="handle", typ=typ.to))
                    if kind == "function":
                        kind, handle = "constructor", made
                elif param.length:
                    outs.append(
                        Out(
                            param=pname,
                            kind="array",
                            typ=typ.to,
                            capacity=param.length,
                            count=param.count,
                        )
                    )
                elif isinstance(self.resolve(typ.to), types.Record):
                    to = self.resolve(typ.to)
                    outs.append(Out(param=pname, kind="record", typ=to))
                else:
                    outs.append(Out(param=pname, kind="value", typ=typ.to))
                args.append(Arg(kind="out", **arg))
                continue

            owned = is_opaque_ptr(typ, self.handles)
            if idx == 0 and owned and kind == "function":
                args.append(Arg(kind="self", **arg))
                kind, handle = "method", owned
                if func.destroys == param.name:
                    kind = "destructor"
                continue

            if types.is_string(typ):
                args.append(Arg(kind="string", **arg))
            elif param.length:
                args.append(Arg(kind="sequence", **arg))
            elif param.name in bound:
                args.append(Arg(kind="callback", lifetime=param.lifetime, **arg))
            else:
                args.append(Arg(kind="value", **arg))

        ret = func.ret
        returns: Returns
        if isinstance(ret, types.Builtin) and ret.name == "void":
            returns = "nothing"
        elif func.errno:
            # @errno was checked to return a signed integer, which has a name
            status = getattr(ret, "name", None) == "int" and not func.counted
            returns = "nothing" if status else "count"
        elif types.is_string(ret):
            returns = "string"
        elif is_opaque_ptr(ret, self.handles) or is_lent(ret):
            returns = "handle"
        elif isinstance(ret, types.Pointer):
            returns = "pointer"
        else:
            returns = "value"

        prefixes = [self.prefix]
        if handle:
            prefixes.append(self.handle_name(handle))
        # The suffix is removed first: 'foo_sized' under the prefix 'foo' is 'foo'
        name = strip(func.name[: -len(SIZED)] if sizes else func.name, *prefixes)

        return Call(
            function=func.name,
            name=name,
            kind=kind,
            handle=handle,
            args=args,
            outs=outs,
            errno=func.errno,
            partial=func.partial,
            returns=returns,
            nullable=func.nullable,
            memory=func.memory,
            ret=ret,
        )

    def functions(self) -> List[Call]:
        return [c for c in self.calls if c.kind == "function"]

    def partner(self, call: Call, role: str) -> Optional[Call]:
        """The call of the role 'role' in the buffer or registration pattern
        of 'call'"""

        if call.memory is None:
            return None
        return next(
            (
                c
                for c in self.calls
                if c.memory
                and c.memory.stem == call.memory.stem
                and c.memory.role == role
            ),
            None,
        )

    def owner(self, release: Call) -> Optional[Call]:
        """The call that allocates or registers what 'release' frees, resizes
        or unregisters"""

        if release.memory is None:
            return None
        role = "register" if release.memory.role == "unregister" else "alloc"
        return self.partner(release, role)

    def of(self, handle: str) -> Dict[str, List[Call]]:
        """The calls of 'handle', by kind"""

        found: Dict[str, List[Call]] = {
            "constructor": [],
            "destructor": [],
            "method": [],
        }
        for call in self.calls:
            if call.handle == handle and call.kind in found:
                found[call.kind].append(call)
        return found
