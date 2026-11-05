"""
What C cannot say about an FFI boundary, taken from the documentation of its
functions, and checked: which way each pointer goes, which may be NULL, which
integer is the length of which pointer, which ``void *`` is the context of which
callback, which functions report errors as a negative errno, and which destroy
the handles others create.

The targets need this to bind the API idiomatically rather than only as raw
calls: to return what a function writes through an [out] pointer, to raise or
return an error, to release a handle when it goes out of scope, and to pass a
closure as a callback. Each is a rule of the C subset, or a tag in the Doxygen
comment of the function:

``@param[in]``, ``@param[out]``, ``@param[in,out]``
  Doxygen's own: whether the function reads what the pointer points to, writes
  it, or both. A pointer documented with neither is read, ``[in]``.

``@nullable name ...``
  The named pointer parameters may be NULL; ``return`` names what the function
  returns. Every other pointer must not be NULL.

``@len pointer count ...``
  The parameter ``count`` holds the number of elements ``pointer`` points to;
  pairs, any number of them.

``@errno``
  The function returns a negative errno on failure, and zero or more on
  success. It returns a signed integer.

``@destroys name``
  The function releases the handle given as ``name``, its only parameter; after
  it, the handle is not used again. An opaque record created through an [out]
  pointer must have one.

``@lifetime callback call|once|handle ...``
  How long the library may invoke the callback, a promise only the author of
  the header can make: ``call``, only during the call; ``once``, at most once,
  after the call, and not at all when it fails; ``handle``, any number of times,
  until the handle the function is a method of is destroyed, and not at all
  when the call fails. Pairs, one for every callback, invoked on the thread
  that called into the library.

A ``void *`` parameter right after a callback is the callback's context, as the
callback-context rule requires; a returned ``const char *`` is borrowed, as the
string-return rule requires.
"""

from typing import Callable, Dict, List, Optional, cast

from . import decls, types
from .doc import DIRECTIONS

SIGNED = (
    "signed char",
    "short",
    "int",
    "long",
    "long long",
    "int8_t",
    "int16_t",
    "int32_t",
    "int64_t",
    "intptr_t",
    "ssize_t",
    "ptrdiff_t",
)
INTEGERS = SIGNED + (
    "unsigned char",
    "unsigned short",
    "unsigned int",
    "unsigned long",
    "unsigned long long",
    "uint8_t",
    "uint16_t",
    "uint32_t",
    "uint64_t",
    "uintptr_t",
    "size_t",
)


def is_void_ptr(typ) -> bool:
    return (
        isinstance(typ, types.Pointer)
        and isinstance(typ.to, types.Builtin)
        and typ.to.name == "void"
    )


def is_integer(typ, kinds=INTEGERS) -> bool:
    return isinstance(typ, types.Builtin) and typ.name in kinds


class Semantics(object):
    """Applies the tags of the functions to the IR, reporting what is wrong"""

    def __init__(self, entities: list, report: Callable[[str, str, object], None]):
        self.entities = entities
        self.report = report
        self.typedefs = {e.name: e for e in entities if isinstance(e, decls.Typedef)}
        self.records = {e.name: e for e in entities if isinstance(e, decls.RECORDS)}

    def renamed_record(self, typ) -> bool:
        """Whether 'typ' reaches a record only through a typedef of another name,
        such as ``foo_t *`` for ``typedef struct foo_s foo_t;``"""

        def resolve(typ):
            while isinstance(typ, types.TypedefRef) and typ.name in self.typedefs:
                typ = self.typedefs[typ.name].typ
            return typ

        direct = isinstance(typ, types.Pointer) and isinstance(typ.to, types.Record)
        typ = resolve(typ)
        to = resolve(typ.to) if isinstance(typ, types.Pointer) else None
        return isinstance(to, types.Record) and not direct

    def callback(self, typ) -> Optional[types.FunctionType]:
        """The function type of 'typ', when it is a pointer to a function"""

        while isinstance(typ, types.TypedefRef) and typ.name in self.typedefs:
            typ = self.typedefs[typ.name].typ
        if isinstance(typ, types.Pointer) and isinstance(typ.to, types.FunctionType):
            return typ.to
        return None

    def opaque(self, record: types.Record) -> bool:
        """Whether the header has 'record' without fields, only to point to"""

        return not any(
            isinstance(e, (decls.Struct, decls.Union))
            and e.name == record.name
            and e.fields
            for e in self.entities
        )

    def is_method(self, func: decls.Function) -> bool:
        """Whether the first parameter of 'func' is a handle, an opaque record"""

        if not func.params:
            return False
        typ = func.params[0].typ
        if not (isinstance(typ, types.Pointer) and isinstance(typ.to, types.Record)):
            return False
        declared = any(
            isinstance(e, (decls.Struct, decls.Union)) and e.name == typ.to.name
            for e in self.entities
        )
        return declared and self.opaque(typ.to)

    def is_pointer(self, typ) -> bool:
        """Whether 'typ' is a pointer, also one by a typedef of a callback"""

        return isinstance(typ, types.Pointer) or self.callback(typ) is not None

    def run(self, cursors: Dict[str, object]):
        for entity in self.entities:
            if isinstance(entity, decls.Function):
                self.function(entity, cursors.get(entity.name))
            elif isinstance(entity, decls.Typedef):
                self.typedef(entity, cursors.get(entity.name))
        self.lifecycle(cursors)

    def typedef(self, typedef: decls.Typedef, cursor):
        func = self.callback(typedef.typ)
        if func is None:
            return
        contexts = [p for p in func.params if is_void_ptr(p.typ)]
        if len(contexts) != 1:
            self.report(
                "callback-context",
                f"callback '{typedef.name}' takes {len(contexts)} void * parameters,"
                " not one context",
                cursor,
            )

    def function(self, func: decls.Function, cursor):
        params = {p.name: p for p in func.params if p.name}
        tags = func.doc.tags

        def annotation(message: str):
            self.report("annotation", f"'{func.name}': {message}", cursor)

        def names(tag: str) -> List[str]:
            return tags.get(tag, "").split()

        if (
            isinstance(func.ret, types.Pointer)
            and isinstance(func.ret.to, types.Builtin)
            and func.ret.to.name == "char"
            and not func.ret.to.const
        ):
            self.report(
                "string-return",
                f"'{func.name}' returns char *; a returned string is const char *",
                cursor,
            )

        for name in func.doc.params:
            if name not in params:
                annotation(f"@param names '{name}', which is not a parameter")
        for name, spelled in func.doc.directions.items():
            param = params.get(name)
            direction = DIRECTIONS.get(spelled)
            if param is None:
                continue
            if direction is None:
                annotation(f"'{name}' is [{spelled}], not [in], [out] or [in,out]")
                continue
            if direction != "in" and not isinstance(param.typ, types.Pointer):
                annotation(f"'{name}' is [{direction}] but is not a pointer")
                continue
            to = param.typ.to if isinstance(param.typ, types.Pointer) else None
            if direction != "in" and isinstance(to, types.Record) and self.opaque(to):
                annotation(
                    f"'{name}' is [{direction}] but points to an opaque record;"
                    " one written is given by a pointer to a pointer"
                )
                continue
            param.direction = direction

        for name in names("nullable"):
            if name == "return":
                if isinstance(func.ret, types.Pointer):
                    func.nullable = True
                else:
                    annotation("@nullable names 'return', which is not a pointer")
            elif name not in params:
                annotation(f"@nullable names '{name}', which is not a parameter")
            elif not self.is_pointer(params[name].typ):
                annotation(f"@nullable names '{name}', which is not a pointer")
            else:
                params[name].nullable = True

        pairs = names("len")
        if len(pairs) % 2:
            annotation("@len takes pairs of a pointer and its count")
        for pointer, count in zip(pairs[::2], pairs[1::2]):
            if pointer in params and params[pointer].length is not None:
                annotation(f"@len names '{pointer}' twice")
            elif pointer not in params or count not in params:
                annotation(f"@len names '{pointer} {count}', not parameters")
            elif self.callback(params[pointer].typ) is not None:
                annotation(f"@len names '{pointer}', which is a callback")
            elif not isinstance(params[pointer].typ, types.Pointer):
                annotation(f"@len names '{pointer}', which is not a pointer")
            elif not is_integer(params[count].typ):
                annotation(f"@len names '{count}', which is not an integer")
            else:
                params[pointer].length = count

        if "errno" in tags:
            if tags["errno"]:
                annotation("@errno takes nothing")
            if is_integer(func.ret, SIGNED):
                func.errno = True
            else:
                annotation("@errno, but it does not return a signed integer")

        if "destroys" in tags:
            name = tags["destroys"]
            typ = params[name].typ if name in params else None
            if typ is None:
                annotation(f"@destroys names '{name}', which is not a parameter")
            elif len(func.params) != 1:
                annotation(
                    f"@destroys names '{name}', but it is not the only parameter"
                )
            elif self.renamed_record(typ):
                annotation(
                    f"@destroys names '{name}', a record through a typedef of another"
                    " name, which is no handle; name the record, or typedef it by"
                    " its own name"
                )
            elif not (
                isinstance(typ, types.Pointer) and isinstance(typ.to, types.Record)
            ):
                annotation(f"@destroys names '{name}', not a pointer to a record")
            else:
                func.destroys = name

        pairs = names("lifetime")
        promised = set(pairs[::2])
        if len(pairs) % 2:
            annotation("@lifetime takes pairs of a callback and its lifetime")
        for name, value in zip(pairs[::2], pairs[1::2]):
            if name in params and params[name].lifetime is not None:
                annotation(f"@lifetime names '{name}' twice")
            elif name not in params or self.callback(params[name].typ) is None:
                annotation(f"@lifetime names '{name}', which is not a callback")
            elif value not in ("call", "once", "handle"):
                annotation(
                    f"@lifetime of '{name}' is '{value}', not call, once or handle"
                )
            elif value == "handle" and not self.is_method(func):
                annotation(f"@lifetime of '{name}' is handle, but there is no handle")
            else:
                params[name].lifetime = cast(decls.Lifetime, value)

        for idx, param in enumerate(func.params):
            fntype = self.callback(param.typ)
            if fntype is None:
                continue
            contexts = [p for p in fntype.params if is_void_ptr(p.typ)]
            if not isinstance(param.typ, types.TypedefRef) and len(contexts) != 1:
                self.report(
                    "callback-context",
                    f"'{func.name}' takes the callback '{param.name}', which takes"
                    f" {len(contexts)} void * parameters, not one",
                    cursor,
                )
            if param.lifetime is None and param.name not in promised:
                self.report(
                    "callback-lifetime",
                    f"'{func.name}' takes the callback '{param.name}' without a"
                    " @lifetime",
                    cursor,
                )
            if len(contexts) != 1:
                continue
            after = func.params[idx + 1] if idx + 1 < len(func.params) else None
            if after is None or not is_void_ptr(after.typ) or not after.name:
                self.report(
                    "callback-context",
                    f"'{func.name}' takes the callback '{param.name}' without a"
                    " void * context after it",
                    cursor,
                )
            else:
                after.context = param.name
                if after.length:
                    annotation(
                        f"'{after.name}' is the context of '{param.name}', which"
                        " the binding passes; it has no @len"
                    )
                    after.length = None

    def lifecycle(self, cursors: Dict[str, object]):
        """Report the records created through an [out] pointer, never destroyed"""

        complete = {
            e.name
            for e in self.entities
            if isinstance(e, (decls.Struct, decls.Union)) and e.fields
        }
        created: Dict[str, decls.Function] = {}
        destroyed = set()
        for func in self.entities:
            if not isinstance(func, decls.Function):
                continue
            for param in func.params:
                typ = param.typ
                if (
                    param.direction == "out"
                    and isinstance(typ, types.Pointer)
                    and isinstance(typ.to, types.Pointer)
                    and isinstance(typ.to.to, types.Record)
                    and typ.to.to.name not in complete
                ):
                    created.setdefault(typ.to.to.name, func)
            if func.destroys:
                typ = next(p.typ for p in func.params if p.name == func.destroys)
                # @destroys was checked to name a pointer to a record
                assert isinstance(typ, types.Pointer) and isinstance(
                    typ.to, types.Record
                )
                destroyed.add(typ.to.name)

        for name, func in created.items():
            if name not in destroyed:
                self.report(
                    "handle-lifecycle",
                    f"'{func.name}' creates {name}, which no function @destroys",
                    cursors.get(func.name),
                )
