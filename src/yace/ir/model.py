"""
The root of the **yace** IR: the :class:`.Meta` describing the API and the
declarations, its entities, in the order the header declares them

The IR is stored as YAML. :func:`.load` and :meth:`.Model.save` read and write
it, and :func:`.schema` is its JSON Schema, for tools that read the IR without
**yace**.
"""

import platform
from pathlib import Path
from typing import List, Optional

import yaml

from . import decls
from .types import Node


class Meta(Node):
    """What the API is called, its prefix, and who it is by and under what license"""

    name: str
    prefix: str
    version: str = "0.0.1"
    brief: str = ""
    description: str = ""
    author: str = ""
    license: str = ""
    header: str = ""  # the name of the header the IR was parsed from
    pkg: str = ""  # its pkg-config name, if any
    abi: str = ""  # the platform whose layout the 'size', 'align' and 'offset' are


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

    def find(self, name: str) -> Optional[object]:
        for entity in self.entities:
            if getattr(entity, "name", None) == name:
                return entity
        return None


def load(path: Path) -> Model:
    """Read the IR from the YAML at 'path'"""

    return Model.model_validate(yaml.safe_load(Path(path).read_text()))


def schema() -> dict:
    """The JSON Schema of the IR"""

    return Model.model_json_schema()
