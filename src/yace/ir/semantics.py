# SPDX-FileCopyrightText: Simon A. F. Lund <os@safl.dk>
#
# SPDX-License-Identifier: GPL-2.0-only

"""
What C cannot say about an FFI boundary, taken from the documentation of its
functions, and checked: which way each pointer goes, which may be NULL, which
integer is the length of which pointer, which pointer is to a record of
arguments, which ``void *`` is the context of which callback, which functions
report errors as a negative errno, and which destroy the handles others create.

The targets need this to bind the API idiomatically rather than only as raw
calls: to return what a function writes through an [out] pointer, to raise or
return an error, to release a handle when it goes out of scope, and to pass a
closure as a callback. Each is a rule of the C subset, or a tag in the Doxygen
comment of the function:

``@param[in]``, ``@param[out]``, ``@param[in,out]``
  Doxygen's own: whether the function reads what the pointer points to, writes
  it, or both. A pointer documented with neither is read, ``[in]``.

``@recparam name text``
  As ``@param``, of a record of arguments: ``name`` is a pointer to a const
  struct, and its size is the ``size_t`` ``<name>_nbytes``, or the parameter
  that ``@nbytes_at{size}`` in the text names. The function's name ends in
  ``_sized``, and a static inline function of the name without it passes
  ``sizeof``.

``@arrparam name text``
  As ``@param``, of an array: its length is the unsigned integer ``<name>_len``,
  or the parameter that ``@len_at{length}`` in the text names. Of an
  [out] array, the length is the capacity, and an [out] pointer to an unsigned
  integer ``<name>_nwritten``, or the one ``@nwritten_at{count}`` names, is the
  number of elements the function wrote. Where ``<name>_len`` or
  ``<name>_nwritten`` is a parameter, no reference names another.

``@nullable name ...``
  The named pointer parameters may be NULL; ``return`` names what the function
  returns. Every other pointer must not be NULL.

``@errno``
  The function returns a negative errno on failure, and zero or more on
  success. It returns a signed integer. ``@errno partial`` says that the
  function writes its [out] parameters also when it fails, so that what it
  wrote is not lost. It returns ``int``, has an [out] parameter, and none is a
  handle.

``@destroys name``
  The function releases the handle given as ``name``, its only parameter; after
  it, the handle is not used again. An opaque record created through an [out]
  pointer must have one.

``@lifetime callback call|once|handle ...``
  How long the library may invoke the callback, a promise only the author of
  the header can make: ``call``, only during the call; ``once``, at most once,
  after the call, and not at all when it fails; ``handle``, any number of times,
  until the handle the function is a method of is destroyed, and not at all
  when the call fails. The tag takes pairs, one for every callback. A callback
  is invoked during a call into the library, on its thread: ``call``, during
  the call itself; the others, of a method, during a later call given the same
  handle, or of a function, during any later call.

``@nobind``
  The function is not bound: the parser leaves it out of the IR, before reading
  its types, which may be outside the C subset, such as the ``FILE *`` of a
  printer. It takes nothing.

A ``void *`` parameter right after a callback is the callback's context, as the
callback-context rule requires; a returned ``const char *`` is borrowed, as the
string-return rule requires.
"""

from typing import Callable, Dict, Iterable, List, Optional, cast

from . import decls, types
from .doc import DIRECTIONS

# The suffix of a function taking a @recparam, which the static inline function
# passing the size has not
SIZED = "_sized"

# The suffixes of the parameters that are, by convention, the size of the
# @recparam of their name, and the length and count written of the @arrparam
NBYTES = "_nbytes"
LEN = "_len"
WRITTEN = "_nwritten"

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
UNSIGNED = (
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
INTEGERS = SIGNED + UNSIGNED


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

    def __init__(
        self,
        entities: list,
        report: Callable[[str, str, object], None],
        inlines: Iterable[str] = (),
    ):
        self.entities = entities
        self.report = report
        self.inlines = set(inlines)  # the static and inline functions, by name
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

    def points_to_struct(self, typ) -> bool:
        """Whether 'typ' is a pointer to a const struct the headers define, which
        has a size, also by a typedef"""

        if not isinstance(typ, types.Pointer) or not getattr(typ.to, "const", False):
            return False
        to = typ.to
        while isinstance(to, types.TypedefRef) and to.name in self.typedefs:
            to = self.typedefs[to.name].typ
        return (
            isinstance(to, types.Record) and to.tag == "struct" and not self.opaque(to)
        )

    def paired(
        self,
        func: decls.Function,
        name: str,
        command: str,
        suffix: str,
        annotation,
        required: bool = True,
    ) -> Optional[decls.Param]:
        """The parameter that the @<command>{} in the text of 'name' names, or
        else the one named '<name><suffix>'; None, reported where 'required',
        when there is neither, and reported when both are parameters and differ,
        as the name of the one would mislead"""

        params = {p.name: p for p in func.params if p.name}
        conventional = f"{name}{suffix}"
        named = func.doc.references.get(name, {}).get(command)
        if named is None and conventional in params:
            return params[conventional]
        if named is None:
            if required:
                annotation(f"'{name}' has no '{conventional}', nor a @{command}{{}}")
            return None
        if named not in params:
            annotation(f"@{command}{{{named}}} of '{name}' names no parameter")
            return None
        if named != conventional and conventional in params:
            annotation(
                f"@{command}{{{named}}} of '{name}', but '{conventional}' is a"
                " parameter too; rename it"
            )
            return None
        return params[named]

    def arrparam(self, func: decls.Function, name: str, annotation, counted: set):
        """Apply the @arrparam 'name' of 'func': a pointer, and its length, an
        unsigned integer, by @len_at{} or '<name>_len'. An [out] one may
        have a count written, an [out] pointer to an unsigned integer, by
        @nwritten_at{} or '<name>_nwritten'; 'counted' holds those already taken"""

        params = {p.name: p for p in func.params if p.name}
        found = func.doc.references.get(name, {})
        array = params.get(name)
        if array is None:
            annotation(f"@arrparam names '{name}', which is not a parameter")
            return
        if name in func.doc.records:
            annotation(f"'{name}' is documented by both @arrparam and @recparam")
            return
        if "nbytes_at" in found:
            annotation(f"'{name}' has @nbytes_at, which is of a @recparam")
            return
        if self.callback(array.typ) is not None:
            annotation(f"@arrparam names '{name}', which is a callback")
            return
        if not isinstance(array.typ, types.Pointer):
            annotation(f"@arrparam names '{name}', which is not a pointer")
            return

        length = self.paired(func, name, "len_at", LEN, annotation)
        if length is None:
            return
        if not is_integer(length.typ, UNSIGNED):
            annotation(
                f"the length '{length.name}' of '{name}' is not an unsigned integer"
            )
            return
        array.length = length.name

        written = self.paired(func, name, "nwritten_at", WRITTEN, annotation, False)
        if written is None:
            return
        if array.direction != "out":
            annotation(
                f"'{written.name}' is the count written of '{name}', which is not"
                " [out]"
            )
        elif not self.is_out_count(written):
            annotation(
                f"the count written '{written.name}' of '{name}' is not an [out]"
                " pointer to an unsigned integer"
            )
        elif written.name in func.doc.arrays:
            annotation(
                f"the count written '{written.name}' of '{name}' is an @arrparam"
            )
        elif written.name in counted:
            annotation(f"'{written.name}' is the count written of two arrays")
        else:
            array.count = written.name
            counted.add(written.name)

    def sized(self, func: decls.Function, annotation) -> bool:
        """Whether the name of 'func', a function taking a @recparam, ends in
        '_sized', and a static inline function of the name without it exists;
        what that function passes is not checked"""

        wrapper = func.name[: -len(SIZED)]
        if not func.name.endswith(SIZED) or not wrapper:
            annotation(f"@recparam, but the name does not end in '{SIZED}'")
        elif wrapper not in self.inlines:
            annotation(
                f"@recparam, but the headers have no static inline '{wrapper}'"
                " that passes the size"
            )
        else:
            return True
        return False

    def recparam(self, func: decls.Function, name: str, annotation, sized: set):
        """Apply the @recparam 'name' of 'func', a function taking its arguments
        as a record: 'name' is an [in] pointer to a const struct the headers
        define, and its size is a size_t, by @nbytes_at{} or '<name>_nbytes';
        'sized' holds the sizes already taken. The record's parameter then holds
        the size's name"""

        params = {p.name: p for p in func.params if p.name}
        found = func.doc.references.get(name, {})
        record = params.get(name)
        if record is None:
            annotation(f"@recparam names '{name}', which is not a parameter")
            return
        if name in func.doc.arrays:
            return  # reported by arrparam()
        others = [f"@{command}" for command in found if command != "nbytes_at"]
        if others:
            annotation(f"'{name}' has {', '.join(others)}, which is of an @arrparam")
            return
        if not self.points_to_struct(record.typ):
            annotation(
                f"@recparam names '{name}', which is not a pointer to a const"
                " struct defined in the headers"
            )
            return
        if func.doc.directions.get(name, "in") != "in":
            annotation(f"@recparam names '{name}', which is not [in]")
            return
        size = self.paired(func, name, "nbytes_at", NBYTES, annotation)
        if size is None:
            return
        if not (isinstance(size.typ, types.Builtin) and size.typ.name == "size_t"):
            annotation(f"the size '{size.name}' of '{name}' is not a size_t")
        elif any(p.length == size.name for p in func.params):
            annotation(
                f"the size '{size.name}' of '{name}' is the length of an array too"
            )
        elif size.name in sized:
            annotation(f"the size '{size.name}' is the size of two records")
        else:
            record.size = size.name
            sized.add(size.name)

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

    def is_out_count(self, param: decls.Param) -> bool:
        """Whether 'param' is an [out] pointer to an unsigned integer"""

        typ = param.typ
        return (
            param.direction == "out"
            and isinstance(typ, types.Pointer)
            and is_integer(typ.to, UNSIGNED)
        )

    def partial(self, func: decls.Function, annotation) -> bool:
        """Whether 'func' can write its [out] parameters when it fails: 'func'
        has an [out] parameter, none of them is a handle, as the owner of a
        handle written by a failed call is undefined, and 'func' returns int, as
        a failure returns no count"""

        outs = [p for p in func.params if p.direction == "out"]
        if not outs:
            annotation("@errno partial, but no parameter is [out]")
            return False
        if getattr(func.ret, "name", None) != "int":
            annotation(
                "@errno partial, but it returns a count, which a failure does not"
                " give; return int, and write the count through an [out] pointer"
            )
            return False
        for param in outs:
            to = param.typ.to if isinstance(param.typ, types.Pointer) else None
            if (
                isinstance(to, types.Pointer)
                and isinstance(to.to, types.Record)
                and self.opaque(to.to)
            ):
                annotation(f"@errno partial, but '{param.name}' is an [out] handle")
                return False
        return True

    def is_pointer(self, typ) -> bool:
        """Whether 'typ' is a pointer, also one by a typedef of a callback"""

        return isinstance(typ, types.Pointer) or self.callback(typ) is not None

    def run(self, cursors: Dict[str, object]):
        for entity in self.entities:
            if isinstance(entity, decls.Function):
                self.function(entity, cursors.get(entity.name))
                continue
            if isinstance(entity, decls.Typedef):
                self.typedef(entity, cursors.get(entity.name))
            self.misplaced(entity, cursors.get(getattr(entity, "name", "")))
        self.lifecycle(cursors)

    def misplaced(self, entity, cursor):
        """Report the @arrparam, @recparam and references in the comments of
        'entity', and of its fields or members, which is no function"""

        docs = [getattr(entity, "doc", None)]
        docs += [f.doc for f in getattr(entity, "fields", None) or []]
        docs += [m.doc for m in getattr(entity, "members", None) or []]
        name = getattr(entity, "name", None)
        for doc in [d for d in docs if d is not None]:
            found = list(doc.stray)
            for references in doc.references.values():
                found += [f"@{cmd}{{{to}}}" for cmd, to in references.items()]
            found += [f"@arrparam {n}" for n in doc.arrays]
            found += [f"@recparam {n}" for n in doc.records]
            for text in found:
                self.report(
                    "annotation",
                    f"'{name}': {text} is in the comment of no function",
                    cursor,
                )

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
            if name not in params and name not in func.doc.records + func.doc.arrays:
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

        if "len" in tags:
            annotation(
                "@len is removed; document the array with @arrparam, its length"
                " named '<array>_len' or by @len_at{}"
            )
        counted: set = set()  # the counts written, of any array
        for name in func.doc.arrays:
            self.arrparam(func, name, annotation, counted)
        for marker in func.doc.stray:
            if "{" in marker:
                annotation(f"{marker} is not in the text of an @arrparam or @recparam")
            else:
                annotation(f"{marker} names no parameter; name it in braces")
        for name, command in func.doc.repeated:
            annotation(f"'{name}' has @{command} twice")
        for name in func.doc.twice:
            annotation(
                f"'{name}' is documented twice, by @arrparam or @recparam and"
                " another tag"
            )
        for name, found in func.doc.references.items():
            if name not in func.doc.arrays and name not in func.doc.records:
                commands = ", ".join(f"@{command}" for command in found)
                annotation(
                    f"'{name}' has {commands}, but is documented by @param, not by"
                    " @arrparam or @recparam"
                )

        # What an [out] void * points to has no size, so nothing says how much
        # the function writes, and no binding can return what was written
        for param in func.params:
            if (
                param.direction == "out"
                and is_void_ptr(param.typ)
                and param.length is None
            ):
                annotation(
                    f"'{param.name}' is [out] but points to void without a length;"
                    " document it with @arrparam, its length in bytes"
                )
                param.direction = "in"

        sized: set = set()  # the sizes, of any record
        for name in func.doc.records:
            self.recparam(func, name, annotation, sized)
        if func.doc.records and not self.sized(func, annotation):
            for param in func.params:
                param.size = None

        if "errno" in tags:
            if tags["errno"] not in ("", "partial"):
                annotation("@errno takes nothing, or 'partial'")
            if is_integer(func.ret, SIGNED):
                func.errno = True
                func.partial = tags["errno"] == "partial" and self.partial(
                    func, annotation
                )
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
                        " the binding passes; a context is no @arrparam"
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
