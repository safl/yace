#!/usr/bin/env python3
"""
The function types consists of:

* Function Declarations: :class:`FunctionDecl`
* Function Pointer Declarations: :class:`FunctionPtrDecl`

This needs a bit more work..
"""
import typing

from .base import Typespec


class Parameter(Typespec):
    """
    Function parameter
    """

    sym: str = "nope"
    doc: str = ""
    cls: str = "param"
    lbl: str = "default"


class Function(Typespec):
    """
    Function declarations
    """

    sym: str = "nope"
    doc: str = ""

    parameters: typing.List[Parameter] = []

    cls: str = "fun"
    lbl: str = "default"


class FunctionPointer(Typespec):
    """
    Function pointer declarations
    """

    ret: typing.Type[Typespec] = None
    parameters: typing.List[Typespec] = []

    cls: str = "fun_ptr"
    lbl: str = "default"
