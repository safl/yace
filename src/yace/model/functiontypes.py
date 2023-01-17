#!/usr/bin/env python3
"""
The function types consists of:

* Function Declarations: :class:`FunctionDecl`
* Function Pointer Declarations: :class:`FunctionPtrDecl`

This needs a bit more work..
"""
import typing
from dataclasses import dataclass, field

from .entities import Entity, Typedecl


@dataclass
class Parameter(Entity):
    """
    Function parameter
    """

    dtype: typing.Type[Typedecl]
    cls: str = "param"
    lbl: str = "default"


@dataclass
class FunctionDecl(Entity):
    """
    Function declarations
    """

    ret: typing.Type[Typedecl]
    parameters: typing.List[Parameter]

    cls: str = "fun"
    lbl: str = "default"


@dataclass
class FunctionPtrDecl(Entity):
    """
    Function pointer declarations
    """

    ret: typing.Type[Typedecl]
    parameters: typing.List[Typedecl]

    cls: str = "fun_ptr"
    lbl: str = "default"
