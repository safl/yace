#!/usr/bin/env python3
"""
The :class:`.Model` provides the root-node for the **Yace** Interface
Definition, it provides helper-functions for loading **Yace** Interface
Definition Language files from their ``.yaml`` format on the file-system, into
the representation offered by the **Yace** Interface Definition
Language-entities.

* :class:`.Meta`
* :class:`.Model`
* :class:`.ModelWalker`

Their **Yace** Interface Definition Language representation follows below.
"""
import inspect
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

import yaml

from yace.errors import InvalidModelData
from yace.idl import base, constants, datatypes, derivedtypes, functiontypes


def data_from_yaml(path: Path) -> Tuple[Dict, List[Dict]]:
    """
    Returns data from YAML (yim) file as (meta, entities)
    """

    meta = {}
    entities = []

    with path.open() as yamlfile:
        for lbl, data in yaml.safe_load(yamlfile).items():
            if lbl == "meta":
                meta = data
                continue

            for entity in data:
                if "lbl" not in entity:
                    entity["lbl"] = []
                entity["lbl"].append(lbl)
                if "ant" not in entity:
                    entity["ant"] = {}
                entities.append(entity)

    return meta, entities


@dataclass
class Meta:
    """
    Meta data used by the to describe attributes of the generated C API and
    bindings/wrappers, such as license, version, and documentation
    """

    lic: str  # License string, this is utilized for SPDX
    version: str = "0.0.1"
    author: str = "Foo Bar <foo@example.com>"
    project: str = "Example"
    prefix: str = "ex"
    brief: str = "yace example"
    full: str = (
        "This description is provided with the default idl-meta, to "
        "change it, then make sure you have a meta-lbl in your yace-file"
    )


class Model(object):
    """
    The :class:`.Model` serves as the root of the "tree" describing
    the interface to generate C API and bindings for.
    """

    MAPPING = {
        obj.cls: obj
        for _, obj in (
            inspect.getmembers(base)
            + inspect.getmembers(constants)
            + inspect.getmembers(datatypes)
            + inspect.getmembers(derivedtypes)
            + inspect.getmembers(functiontypes)
        )
        if inspect.isclass(obj) and hasattr(obj, "cls")
    }

    def __init__(self):
        self.meta = Meta(lic="UNLICENSED")
        self.entities = []

    @classmethod
    def entity_from_data(cls, cur: dict, parent=None, depth=0):
        """
        Walk 'cur' recursively with depth-count and "short-hand" expansion

        A tree-walk is needed as just invoking the dataclass-constructor::

            entity = Model.MAPPING["struct"](data)

        Would not instantiate members, parameters, typ, etc. additionally,
        the short-hands are expanded:

        - Integer literals

          - {typ: 10} instead of {typ: {cls: dec, val: 10}}

        - Data Types

          - {typ: u16} instead of {typ: {cls: u16}}

        Foo...
        """

        if type(cur) not in [int, str, dict]:
            raise InvalidModelData(f"Invalid type: {cur}")
        elif type(cur) in [dict] and "cls" not in cur:
            raise InvalidModelData(f"Missing 'cls' in {cur}")

        if isinstance(cur, int):  # short-hand for integer-literal
            return constants.Dec({"lit": cur})
        elif isinstance(cur, str):  # short-hand for typ
            typ = Model.MAPPING.get(cur)
            if not typ:
                raise InvalidModelData(f"typ !short-hand: '{cur}'")

            return typ({})

        constructor = Model.MAPPING.get(cur["cls"])
        if not constructor:
            raise InvalidModelData(f"No constructor for '{cur}'")

        attributes = {}
        for attr, attr_data in cur.items():
            if attr in ["typ", "ret", "val"]:
                attributes[attr] = Model.entity_from_data(attr_data, cur, depth)
            elif attr in ["members", "parameters"]:
                attributes[attr] = [
                    Model.entity_from_data(child, cur, depth + 1)
                    for child in cur.get(attr)
                ]
            else:
                attributes[attr] = attr_data

        return constructor(attributes)

    @classmethod
    def from_data(cls, meta: dict, ents: list):
        """Construct a :class:`Model` using the given 'meta' and 'entities'"""

        interface = cls()
        interface.meta = Meta(**meta)

        total = len(ents)
        for count, entity_data in enumerate(ents, 1):
            logging.debug(f"Processing {count} / {total} in {entity_data['lbl']}")
            entity = cls.entity_from_data(entity_data)
            interface.entities.append(entity)

        return interface

    @classmethod
    def from_path(cls, path: Path):
        """
        Returns a dict composed of the merged content of all yaml-files in the
        given 'path'
        """

        return cls.from_data(*data_from_yaml(path))


class ModelWalker(object):
    """
    Base-class for walking the :class:`.Model`

    This is useful for inspecting properties of the model.

    **HOWTO**: sub-class this and implement the visit() method
    """

    def __init__(self, model):
        self.model = model

    def _traverse(
        self,
        cur,
        ancestors: List,
        depth: int = 0,
    ) -> str:
        """
        Recursive walk of the 'cur' entity, returning a list of visit()
        results.
        """

        res = [self.visit(cur, ancestors, depth)]
        for attr in ["members", "parameters", "typ", "ret", "val"]:
            other = getattr(cur, attr, None)
            if other is None:
                continue

            if attr in ["members", "parameters"]:
                for child in other:
                    res += self._traverse(child, ancestors + [cur], depth + 1)
            else:
                res += self._traverse(other, ancestors + [cur], depth + 1)

        return res

    def walk(self):
        """Walks the :class:`.Model` invoking visit()"""

        status = []
        for entity in self.model.entities:
            status += self._traverse(entity, [], 0)

        return status

    def visit(self, current, ancestors, depth):
        """This is the thing which class should implement"""

        return (True, None)
