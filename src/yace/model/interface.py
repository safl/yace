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

import yaml

from ..errors import InvalidInterfaceModelData
from . import datatypes, entities, enumtypes, literals, macros, structtypes, uniontypes


@dataclass
class Meta:
    """
    Meta data used by the :class:`.emitter.Emitter` to describe attributes of
    the generated C API and bindings/wrappers, such as license, version, and
    documentation
    """

    lic: str  # License string, this is utilized for SPDX
    project: str = "example"
    version: str = "0.0.1"
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
        )
        if inspect.isclass(obj) and hasattr(obj, "cls")
    }

    def __init__(self):

        self.meta = Meta(lic="UNLICENSED")
        self.entities = []

    @classmethod
    def entity_from_data(cls, data: dict):
        """
        Factory function instantiating entities from data

        The entities are constructed using the mapping in
        InterfaceModel.MAPPING, e.g.::

            entity = InterfaceModel.MAPPING["struct"](data)
        """

        constructor = InterfaceModel.MAPPING.get(data["cls"])
        if not constructor:
            raise InvalidInterfaceModelData(f"No mapping for {data}")

        for attr in ["dtype", "lit"]:
            if attr not in data:
                continue

            adata = data.get(attr)
            if isinstance(adata, dict):
                data[attr] = cls.entity_from_data(adata)
            elif isinstance(adata, str) and attr == "dtype":
                constructor_dtype = InterfaceModel.MAPPING.get(adata)
                if not constructor_dtype:
                    raise InvalidInterfaceModelData(
                        f"No mapping for dtype shorthand: {adata}"
                    )
                data[attr] = constructor_dtype()
            elif isinstance(adata, int) and attr == "lit":
                data[attr] = literals.LiteralDec(val=adata)
            elif isinstance(adata, str) and attr == "lit":
                data[attr] = literals.LiteralString(val=adata)
            else:
                raise InvalidInterfaceModelData(f"Invalid {data}")

        if "members" in data:
            data["members"] = [cls.entity_from_data(mdata) for mdata in data["members"]]
            if None in data["members"]:
                raise InvalidInterfaceModelData(f"Issues with {data}")

        return constructor(**data)

    @classmethod
    def from_data(cls, data: dict):
        """Construct an InterfaceModel using the given 'data'"""

        interface = cls()

        meta_data = data.get("meta", None)
        if meta_data:
            del data["meta"]
            interface.meta = Meta(**meta_data)

        for label, ents in data.items():
            total = len(ents)
            for count, entity_data in enumerate(ents, 1):
                logging.info(f"Processing entity {count} / {total} in {label}")
                entity = cls.entity_from_data(entity_data)
                interface.entities.append(entity)

        return interface

    @classmethod
    def from_path(cls, path: Path):
        """
        Returns a dict composed of the merged content of all yaml-files in the
        given 'path'
        """

        raw = {}
        with path.open() as sfd:
            for key, val in yaml.safe_load(sfd).items():
                if key not in raw:
                    raw[key] = val
                elif key in raw and isinstance(val, list):
                    raw[key] += val
                else:
                    raw[key].update(val)

        return cls.from_data(raw)
