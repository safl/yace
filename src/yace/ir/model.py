# SPDX-FileCopyrightText: Simon A. F. Lund <os@safl.dk>
#
# SPDX-License-Identifier: GPL-2.0-only

"""
The root of the **yace** IR: the :class:`.Meta` describing the API and the
declarations, its entities, in the order the header declares them

The IR is stored as YAML. :func:`.load` and :meth:`.Model.save` read and write
it, and :func:`.schema` is its JSON Schema, for tools that read the IR without
**yace**.
"""

import platform
from pathlib import Path
from typing import Any, List, Optional, Tuple, Type, TypeVar, overload

import yaml

from . import decls, types
from .types import Node

T = TypeVar("T")
U = TypeVar("U")


class Meta(Node):
    """What the API is called, its prefix, and who it is by and under what license"""

    name: str
    prefix: str
    version: str = "0.0.1"
    brief: str = ""
    description: str = ""
    author: str = ""
    license: str = ""
    headers: List[str] = []  # the names of the headers the IR was parsed from
    prelude: List[str] = []  # system headers included ahead of them, as 'stdio.h'
    pkg: str = ""  # its pkg-config name, if any
    crate: str = ""  # the name of its Rust crate, as 'foo-sys'; else the prefix
    # the function that returns the message of the call that failed last on the
    # calling thread, a 'const char *f(void)', as 'foo_errmsg'; else none
    errmsg: str = ""
    abi: str = ""  # the platform whose layout the 'size', 'align' and 'offset' are

    def source(self) -> str:
        """What the IR was parsed from, as generated code says it"""

        if not self.headers:
            return "the IR"
        if len(self.headers) == 1:
            return self.headers[0]
        others = len(self.headers) - 1
        return f"{self.headers[0]} and {others} other header{'s' * (others > 1)}"


def host_abi() -> str:
    """The platform layout recorded in the IR is valid for, such as 'Linux-x86_64'"""

    return f"{platform.system()}-{platform.machine()}"


class Model(Node):
    meta: Meta
    entities: List[decls.Entity] = []

    def save(self, path: Path):
        """Write the IR to 'path' as YAML"""

        data = self.model_dump(mode="json", exclude_defaults=True)
        data["meta"] = self.meta.model_dump(mode="json")
        path.write_text(yaml.safe_dump(data, sort_keys=False, width=88))

    def records(self) -> dict:
        """The structs and unions by name"""

        return {e.name: e for e in self.entities if isinstance(e, decls.RECORDS)}

    def typedefs(self) -> dict:
        """The typedefs by name"""

        return {e.name: e for e in self.entities if isinstance(e, decls.Typedef)}

    def enums(self) -> dict:
        """The enums by name"""

        return {e.name: e for e in self.entities if isinstance(e, decls.Enum)}

    def errmsg_unfit(self) -> Optional[str]:
        """Why the function that the meta names as 'errmsg' cannot give the
        message of a failed call, or None where the function can, or the meta
        names no function"""

        name = self.meta.errmsg
        if not name:
            return None
        func = self.find(name, decls.Function)
        if func is None:
            return f"'errmsg' names '{name}', which is no function of the API"
        if func.params or func.variadic:
            return f"'errmsg' names '{name}', which takes parameters; it must take void"
        if not types.is_string(func.ret):
            return f"'errmsg' names '{name}', which does not return const char *"
        return None

    def errmsg(self) -> Optional[decls.Function]:
        """The function that returns the message of the call that failed last,
        or None where the meta names none, or one that errmsg_unfit() rejects"""

        if not self.meta.errmsg or self.errmsg_unfit():
            return None
        return self.find(self.meta.errmsg, decls.Function)

    @overload
    def find(self, name: str, kind: Type[T]) -> Optional[T]: ...

    @overload
    def find(self, name: str, kind: Tuple[Type[T], Type[U]]) -> Optional[T | U]: ...

    @overload
    def find(self, name: str, kind: None = None) -> Optional[Any]: ...

    def find(self, name: str, kind: Any = None) -> Optional[Any]:
        """The entity named 'name', of 'kind' where given, as C has records and
        functions of the same name"""

        for entity in self.entities:
            if kind is not None and not isinstance(entity, kind):
                continue
            if getattr(entity, "name", None) == name:
                return entity
        return None


def load(path: Path) -> Model:
    """Read the IR from the YAML at 'path'"""

    return Model.model_validate(yaml.safe_load(Path(path).read_text()))


def schema() -> dict:
    """The JSON Schema of the IR"""

    return Model.model_json_schema()
