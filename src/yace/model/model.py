#!/usr/bin/env python3
"""
A single class (:class:`.Model`) is provided it encapsulates the
loading of the interface model from YAML files into a Pythonic representation
"""
import inspect
import logging
import typing
from dataclasses import dataclass
from pathlib import Path
from pprint import pprint

import yaml

from ..errors import InvalidModelData
from . import (
    datatypes,
    entities,
    enumtypes,
    functiontypes,
    literals,
    macros,
    structtypes,
    uniontypes,
)


def data_from_yaml(path: Path) -> (dict, list):
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
                entity["lbl"] = lbl
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
        "This description is provided with the default model-meta, to "
        "change it, then make sure you have a meta-lbl in your model. "
        "meta: {lic: '"
    )


class Model(object):
    """
    The :class:`.Model` serves as the root of the "tree" describing
    the interface to generate C API and bindings for.
    """

    MAPPING = {
        obj.cls: obj
        for _, obj in (
            inspect.getmembers(entities)
            + inspect.getmembers(macros)
            + inspect.getmembers(datatypes)
            + inspect.getmembers(enumtypes)
            + inspect.getmembers(structtypes)
            + inspect.getmembers(uniontypes)
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

        Would not instantiate members, parameters, dtype, etc. additionally,
        the short-hands are expanded:

        - Integer literals

          - {dtype: 10} instead of {dtype: {cls: dec, val: 10}}

        - Data Types

          - {dtype: u16} instead of {dtype: {cls: u16}}

        Foo...
        """

        if type(cur) not in [int, str, dict]:
            raise InvalidModelData(f"Invalid type: {cur}")
        elif type(cur) in [dict] and "cls" not in cur:
            raise InvalidModelData(f"Missing 'cls' in {cur}")

        if isinstance(cur, int):  # short-hand for integer-literal
            return literals.LiteralDec(lit=cur)
        elif isinstance(cur, str):  # short-hand for dtype
            dtype = Model.MAPPING.get(cur)
            if not dtype:
                raise InvalidModelData(f"dtype !short-hand: '{cur}'")

            return dtype()

        constructor = Model.MAPPING.get(cur["cls"])
        if not constructor:
            raise InvalidModelData(f"No constructor for '{cur}'")

        attributes = {}
        for attr, attr_data in cur.items():
            if attr in ["dtype", "ret", "val"]:
                attributes[attr] = Model.entity_from_data(attr_data, cur, depth)
            elif attr in ["members", "parameters"]:
                attributes[attr] = [
                    Model.entity_from_data(child, cur, depth + 1)
                    for child in cur.get(attr)
                ]
            else:
                attributes[attr] = attr_data

        return constructor(**attributes)

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
    Base-class for walking the interface-model, sub-class this and implement
    the visit() method!
    """

    def _traverse(
        self,
        cur: entities.Entity,
        ancestors: typing.List[entities.Entity],
        depth: int = 0,
    ) -> str:
        """
        Recursive walk of the 'cur' entity, returning a list of visit()
        results.
        """

        res = [self.visit(cur, ancestors, depth)]
        for attr in ["members", "parameters", "dtype", "ret", "val"]:
            other = getattr(cur, attr, None)
            if other is None:
                continue

            if attr in ["members", "parameters"]:
                for child in other:
                    res += self._traverse(child, ancestors + [cur], depth + 1)
            else:
                res += self._traverse(other, ancestors + [cur], depth + 1)

        return res

    def walk(self, model):
        """Walks the :class:`.Model` invoking visit()"""

        status = []
        for entity in model.entities:
            status += self._traverse(entity, [], 0)

        return status

    def visit(self, current, ancestors, depth):
        """This is the thing which class should implement"""

        return (True, None)
