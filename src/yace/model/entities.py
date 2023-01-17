#!/usr/bin/env python3
"""
Two baseclasses are provided:

* :class:`.Entity`
* :class:`.Typedecl`, a base class for type definitions

Entities are the base classes representing the language constructs of C APIs in
the :class:`yace.model.interface.Model`. The entities serve as encapsulated
type-checking of YAML-definitions of the language model.
"""
import typing
from dataclasses import dataclass, field


@dataclass
class Typedecl:
    """
    Representation of a type declaration with modifiers for:

    * const
    * static
    * pointer
    * array
    """

    cls: str
    doc: str = ""
    lbl: str = "typedecl"

    const: bool = False
    static: bool = False
    pointer: int = 0
    array: int = 0

    def is_valid(self):
        """Perform an integrity check of the :class:`.Typedecl`"""

        return (True, None)


@dataclass
class Void(Typedecl):
    """A void, that is, the type signaling no type"""

    cls: str = "void"
    width: int = 0


@dataclass
class Entity:
    """Base class for entities containing common fields"""

    sym: str
    doc: typing.Optional[str]

    def is_valid(self):
        """Perform an integrity check of the :class:`.Entity`"""

        return (True, None)
