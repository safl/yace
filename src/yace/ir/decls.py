"""
Declarations in the **yace** IR, the entities of a :class:`yace.ir.model.Model`

Each is one top-level declaration of the header, in the order they appear:

* :class:`.Include`, ``#include <stdint.h>``
* :class:`.Define`, ``#define FOO_MAX 42``
* :class:`.Enum`, ``enum foo_opt { ... };``
* :class:`.Struct` and :class:`.Union`, ``struct foo { ... };``
* :class:`.Typedef`, ``typedef int (*foo_cb)(void *arg);``
* :class:`.Function`, ``int foo_open(const char *path);``

Struct and union carry their layout, size and alignment in bytes and the offset
of each field in bits, as the compiler that parsed the header laid them out. Targets
check what they generate against it.
"""

import typing
from typing import Annotated, List, Literal, Optional

from pydantic import Field as PydanticField

from .doc import Doc
from .types import Builtin, Node, Type


class Include(Node):
    key: Literal["include"] = "include"
    name: str
    system: bool = True  # <name>, rather than "name"


class IntLiteral(Node):
    key: Literal["int"] = "int"
    value: int
    base: Literal[10, 16] = 10


class StrLiteral(Node):
    key: Literal["str"] = "str"
    value: str


class Define(Node):
    key: Literal["define"] = "define"
    name: str
    value: Annotated[
        typing.Union[IntLiteral, StrLiteral], PydanticField(discriminator="key")
    ]
    doc: Doc = Doc()


class EnumMember(Node):
    name: str
    value: int
    doc: Doc = Doc()


class Enum(Node):
    key: Literal["enum_decl"] = "enum_decl"
    name: str
    members: List[EnumMember]
    underlying: Optional[Builtin] = None
    doc: Doc = Doc()


class Field(Node):
    name: str
    typ: Type
    bits: Optional[int] = None  # the width of a bit-field
    offset: Optional[int] = None  # in bits, from the start of the record
    doc: Doc = Doc()


class Struct(Node):
    key: Literal["struct_decl"] = "struct_decl"
    name: str
    fields: List[Field]
    size: Optional[int] = None  # bytes
    align: Optional[int] = None  # bytes
    doc: Doc = Doc()


class Union(Node):
    key: Literal["union_decl"] = "union_decl"
    name: str
    fields: List[Field]
    size: Optional[int] = None
    align: Optional[int] = None
    doc: Doc = Doc()


class Typedef(Node):
    key: Literal["typedef_decl"] = "typedef_decl"
    name: str
    typ: Type
    doc: Doc = Doc()


class Param(Node):
    """
    A parameter, with what C cannot say about it, from its documentation: whether
    the function reads it, writes it, or both, whether it may be NULL, which
    parameter holds its length, which callback a ``void *`` is the context of,
    and how long a callback may be invoked
    """

    name: str = ""
    typ: Type
    direction: Literal["in", "out", "inout"] = "in"
    nullable: bool = False
    length: Optional[str] = None  # the parameter holding its number of elements
    context: Optional[str] = None  # the callback parameter it is given back to
    lifetime: Optional[Literal["call", "once", "handle"]] = None


class Function(Node):
    """
    A function, with what C cannot say about it, from its documentation: whether
    it returns a negative errno on failure, which parameter's handle it destroys,
    and whether the pointer it returns may be NULL
    """

    key: Literal["function_decl"] = "function_decl"
    name: str
    ret: Type
    params: List[Param] = []
    variadic: bool = False
    errno: bool = False
    destroys: Optional[str] = None
    nullable: bool = False
    doc: Doc = Doc()


Entity = Annotated[
    typing.Union[Include, Define, Enum, Struct, Union, Typedef, Function],
    PydanticField(discriminator="key"),
]

RECORDS = (Struct, Union)
