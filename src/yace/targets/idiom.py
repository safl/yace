# SPDX-FileCopyrightText: Simon A. F. Lund <os@safl.dk>
#
# SPDX-License-Identifier: GPL-2.0-only

"""
How the functions of an API are called idiomatically, in any language, from
what the IR knows of them; each target renders it in its own language.

From the semantics of the C subset, see :py:mod:`yace.ir.semantics`:

* An opaque record is a handle, also by a typedef of its own name, such as
  ``typedef struct foo foo;``. A function creating one through an ``[out]``
  pointer constructs it, the one that ``@destroys`` it releases it, and those
  taking it as their first parameter are its methods. The rest are functions.
* What a function writes through an ``[out]`` pointer is returned, not passed:
  a record, a value, a handle, or the elements of an array, as many as the
  function says it wrote.
* An array read through a pointer is given as a sequence, its ``@len`` count
  then known from the sequence, and not given.
* A callback is given as a closure, kept for as long as its ``@lifetime`` says;
  its ``void *`` context is the binding's to pass, not given. A callback without
  a ``@lifetime`` is given as the raw function pointer, with its context.
* With ``@errno``, a negative return is an error. A function returning ``int``
  returns only that status, so nothing when it succeeds; any other integer is
  a value, such as a count, and returned.
* A returned ``const char *`` is a string, and a returned pointer that is
  ``@nullable`` is nothing when NULL.

Names lose the prefix of the API, and methods also the name of their handle:
``foo_handle_close()`` is the method ``close`` of ``handle``.
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


def is_lent(ret) -> bool:
    """Whether a returned pointer is to a record the caller may write: an object
    the library keeps or hands over, of which a copy would be another object"""

    return (
        isinstance(ret, types.Pointer)
        and isinstance(ret.to, types.Record)
        and not ret.to.const
    )


class Arg(BaseModel):
    """How a parameter of the C function is given, when called idiomatically"""

    param: str  # name of the C parameter
    index: int
    kind: Literal[
        "self",  # the handle the method is called on
        "value",  # given as is
        "string",  # a const char *, given as a string
        "sequence",  # a pointer and @len count, given as a sequence
        "callback",  # a callback, given as a closure
        "length",  # the count of a sequence; not given
        "context",  # the void * context of a callback; not given
        "capacity",  # the count of an [out] array; given, as how many to get
        "out",  # written by the function; returned, not given
    ]
    typ: types.Type
    nullable: bool = False
    of: Optional[str] = None  # the param a length, context or capacity belongs to
    shared: List[str] = []  # the other sequences a length or capacity is of
    lifetime: Optional[str] = None  # of a callback


class Out(BaseModel):
    """What the idiomatic function returns for an [out] parameter"""

    param: str
    kind: Literal["record", "value", "handle", "array"]
    typ: types.Type  # the type written: the record, value, handle or element
    capacity: Optional[str] = None  # for an array, the parameter of its count


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
    returns: Returns
    nullable: bool = False  # whether what is returned may be nothing
    ret: types.Type

    def given(self) -> List[Arg]:
        """The arguments the caller gives; the binding passes or returns the rest"""

        return [a for a in self.args if a.kind in GIVEN]


# The kinds of argument the caller gives
GIVEN = ("value", "string", "sequence", "callback", "capacity")


def call_doc(call: Call, doc: Doc, pname: Callable[[str], str]) -> Tuple[Doc, str]:
    """The doc of 'call', and what it fails with: the parameters given, by their
    names in the binding, and with @errno, what the C function says it returns,
    as how it fails, since the binding returns the value and fails with the
    error; the text says both, and cannot be split"""

    params = {
        pname(a.param): doc.params[a.param]
        for a in call.given()
        if a.param in doc.params
    }
    if not call.errno:
        return doc.model_copy(update={"params": params}), ""
    errors = f"{call.function}() returns: {doc.returns}" if doc.returns else ""
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
    """The name of a local made for the parameter 'name': 'name_suffix', unless
    'taken', by another parameter say, then with '_' until it is not; so long
    as no suffix ends in '_' and another, no two locals share a name"""

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
        is of both, as some targets place it in the handle"""

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
        """The function of the C name 'function', which a record may share"""

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
        """The idiomatic name of a handle, without the prefix: 'handle'"""

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

            if param.direction == "out" and isinstance(typ, types.Pointer):
                made = is_opaque_ptr(typ.to, self.handles)
                if made:
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
            returns = "nothing" if getattr(ret, "name", None) == "int" else "count"
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
        name = strip(func.name, *prefixes)

        return Call(
            function=func.name,
            name=name,
            kind=kind,
            handle=handle,
            args=args,
            outs=outs,
            errno=func.errno,
            returns=returns,
            nullable=func.nullable,
            ret=ret,
        )

    def functions(self) -> List[Call]:
        return [c for c in self.calls if c.kind == "function"]

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
