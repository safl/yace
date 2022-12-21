#!/usr/bin/env python3
"""
Interface

Lorem ipsum dolor sit amet, consectetur adipiscing elit. Pellentesque malesuada
mauris gravida nibh sagittis, sit amet mollis risus luctus. Aliquam et commodo
leo.

Curabitur turpis lacus, consectetur sit amet massa et, porta blandit mi.
Aenean elementum eros tempor, gravida elit ac, faucibus mauris. Maecenas
commodo eleifend ante, nec vestibulum sem aliquam at.
"""
import yaml
import logging
import typing
from dataclasses import dataclass
from pathlib import Path
from yace.model.entities import *

class Interface(object):
    """
    The interface serves as the root of the data-model "tree". The data-model
    is populated by a collection of YAML-files via the classmethod
    Interface.from_data().
    """

    mapping = {
        "define": Define,
        "const": Constant,
        "enum": Enumeration,

        "bits": Bits,
        "bitfield": Bitfield,

        "field": Field,
        "struct": Struct,
        "union": Union,
    }

    def __init__(self):

        self.entities = []

    @classmethod
    def entity_from_data(cls, data: dict):
        """Factory function instantiating entities from data"""

        entity = Interface.mapping.get(data["cls"])
        if not entity:
            return None

        if "members" in data:
            data["members"] = [
                cls.entity_from_data(member_data)
                for member_data in data["members"]
            ]

        return entity(**data)


    @classmethod
    def from_data(cls, data: dict):
        """Construct an InterfaceModel using the given 'data'"""

        interface = cls()

        for label, entities in data.items():
            for entity_data in entities:
                entity = cls.entity_from_data(entity_data)
                interface.entities.append(entity)

        logging.info("got %d", len(interface.entities))

        return interface

    @classmethod
    def from_path(cls, path: Path):
        """
        Returns a dict composed of the merged content of all yaml-files in the
        given 'path'
        """

        raw = {}
        for path in sorted(list(path.glob("**/*.yaml"))):
            with path.open() as sfd:
                for key, val in yaml.safe_load(sfd).items():
                    if key not in raw:
                        raw[key] = val
                    elif key in raw and isinstance(val, list):
                        raw[key] += val
                    else:
                        raw[key].update(val)

        return cls.from_data(raw)
