# SPDX-FileCopyrightText: Simon A. F. Lund <os@safl.dk>
#
# SPDX-License-Identifier: GPL-2.0-only

"""
Types in the **yace** IR

A type is a tree of nodes, each one kind of type, told apart by ``key``:

* :class:`.Builtin`, a type C provides, such as ``int`` or ``uint32_t``
* :class:`.Pointer`, a pointer to another type
* :class:`.Array`, a fixed-length array of another type
* :class:`.Record`, a reference to a ``struct`` or ``union`` by its tag
* :class:`.EnumRef`, a reference to an ``enum`` by its tag
* :class:`.TypedefRef`, a reference to a ``typedef`` by its name
* :class:`.FunctionType`, the signature of a function, the pointee of a
  function pointer

So ``const char *`` is a :class:`.Pointer` to a const :class:`.Builtin` named
``char``, and ``int (*)(void *, size_t)`` is a :class:`.Pointer` to a
:class:`.FunctionType`.
"""

from typing import Annotated, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, model_serializer

BUILTINS = (
    "void",
    "bool",
    "char",
    "signed char",
    "unsigned char",
    "short",
    "unsigned short",
    "int",
    "unsigned int",
    "long",
    "unsigned long",
    "long long",
    "unsigned long long",
    "float",
    "double",
    "int8_t",
    "int16_t",
    "int32_t",
    "int64_t",
    "uint8_t",
    "uint16_t",
    "uint32_t",
    "uint64_t",
    "intptr_t",
    "uintptr_t",
    "size_t",
    "ssize_t",
    "ptrdiff_t",
)

BuiltinName = Literal[BUILTINS]  # type: ignore[valid-type]


class Node(BaseModel):
    """Base of the IR models; unknown attributes are an error, not ignored"""

    model_config = ConfigDict(extra="forbid")

    @model_serializer(mode="wrap")
    def _key_first(self, handler):
        """Keep 'key', first, when defaults are excluded; it tells the kinds apart"""

        data = handler(self)
        if "key" in type(self).model_fields and isinstance(data, dict):
            data = {"key": getattr(self, "key"), **data}
        return data


class Builtin(Node):
    key: Literal["builtin"] = "builtin"
    name: BuiltinName
    const: bool = False


class Pointer(Node):
    key: Literal["pointer"] = "pointer"
    to: "Type"
    const: bool = False  # the pointer itself, as in 'int *const'


class Array(Node):
    key: Literal["array"] = "array"
    of: "Type"
    length: Optional[int]  # None is a flexible array member, 'int data[]'


class Record(Node):
    key: Literal["record"] = "record"
    tag: Literal["struct", "union"]
    name: str
    const: bool = False


class EnumRef(Node):
    key: Literal["enum"] = "enum"
    name: str
    const: bool = False


class TypedefRef(Node):
    key: Literal["typedef"] = "typedef"
    name: str
    const: bool = False


class TypeParam(Node):
    """A parameter of a :class:`.FunctionType`; the name may be empty"""

    name: str = ""
    typ: "Type"


class FunctionType(Node):
    key: Literal["function"] = "function"
    ret: "Type"
    params: List[TypeParam] = []
    variadic: bool = False


Type = Annotated[
    Union[Builtin, Pointer, Array, Record, EnumRef, TypedefRef, FunctionType],
    Field(discriminator="key"),
]

for _model in (Pointer, Array, TypeParam, FunctionType):
    _model.model_rebuild()


def walk(typ):
    """Yield 'typ' and every type nested in it, outermost first"""

    yield typ
    if isinstance(typ, Pointer):
        yield from walk(typ.to)
    elif isinstance(typ, Array):
        yield from walk(typ.of)
    elif isinstance(typ, FunctionType):
        yield from walk(typ.ret)
        for param in typ.params:
            yield from walk(param.typ)


def is_string(typ) -> bool:
    """Whether 'typ' is a ``const char *``, a C string the callee does not change"""

    return (
        isinstance(typ, Pointer)
        and isinstance(typ.to, Builtin)
        and typ.to.name == "char"
        and typ.to.const
    )
