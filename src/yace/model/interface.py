#!/usr/bin/env python3
"""
A single class (:class:`.InterfaceModel`) is provided it encapsulates the
loading of the interface model from YAML files into a Pythonic representation
"""
import inspect
import logging
import typing
from dataclasses import dataclass
from pathlib import Path
from pprint import pprint

import yaml

from ..errors import InvalidInterfaceModelData
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
        for label, data in yaml.safe_load(yamlfile).items():
            if label == "meta":
                meta = data
                continue

            for entity in data:
                entity["label"] = label
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
        "change it, then make sure you have a meta-label in your model. "
        "meta: {lic: '"
    )


class InterfaceModel(object):
    """
    The :class:`.InterfaceModel` serves as the root of the "tree" describing
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

    def traverse(
        self,
        current: entities.Entity,
        parent: typing.Optional[entities.Entity],
        depth: int = 0,
    ) -> str:
        """
        Recursive walk of the 'current' entity
        """

        self.func(current.cls, parent, depth)
        if getattr(current, "members", None):
            for member in getattr(current, "members"):
                self.traverse(member, current, depth + 1)

    @classmethod
    def entity_from_data(cls, cur: dict, parent=None, depth=0):
        """
        Walk 'cur' recursively with depth-count and "short-hand" expansion

        A tree-walk is needed as just invoking the dataclass-constructor::

            entity = InterfaceModel.MAPPING["struct"](data)

        Would not instantiate members, parameters, dtype, etc. additionally,
        the short-hands are expanded:

        - Integer literals

          - {dtype: 10} instead of {dtype: {cls: dec, val: 10}}

        - Data Types

          - {dtype: u16} instead of {dtype: {cls: u16}}

        Foo...
        """

        if type(cur) not in [int, str, dict]:
            raise InvalidInterfaceModelData(f"Invalid type: {cur}")
        elif type(cur) in [dict] and "cls" not in cur:
            raise InvalidInterfaceModelData(f"Missing 'cls' in {cur}")

        if isinstance(cur, int):  # short-hand for integer-literal
            return literals.LiteralDec(val=cur)
        elif isinstance(cur, str):  # short-hand for dtype
            dtype = InterfaceModel.MAPPING.get(cur)
            if not dtype:
                raise InvalidInterfaceModelData(f"dtype !short-hand: '{cur}'")

            return dtype()

        constructor = InterfaceModel.MAPPING.get(cur["cls"])
        if not constructor:
            raise InvalidInterfaceModelData(f"No constructor for '{cur}'")

        attributes = {}
        for attr, attr_data in cur.items():
            if attr in ["dtype", "ret", "lit"]:
                attributes[attr] = InterfaceModel.entity_from_data(
                    attr_data, cur, depth
                )
            elif attr in ["members", "parameters"]:
                attributes[attr] = [
                    InterfaceModel.entity_from_data(child, cur, depth + 1)
                    for child in cur.get(attr)
                ]
            else:
                attributes[attr] = attr_data

        return constructor(**attributes)

    @classmethod
    def from_data(cls, meta: dict, entities: list):
        """Construct an InterfaceModel using the given 'meta' and 'entities'"""

        interface = cls()
        interface.meta = Meta(**meta)

        total = len(entities)
        for count, entity_data in enumerate(entities, 1):
            logging.debug(f"Processing {count} / {total} in {entity_data['label']}")
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
