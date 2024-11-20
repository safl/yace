#!/usr/bin/env python3
"""
The **yace** function types consists of:

* Function Declarations: :class:`.Function`
* Function Pointer Declarations: :class:`.FunctionPointer`
* Both of the above make use of

  * :class:`.Parameter`
  * :class:`.ReturnType`

Their Yace-Intermediate-Representation follows below.
"""
import typing

from .base import Documented, Entity, Named
from .datatypes import Typed, Typespec


class Parameter(Entity, Named, Typed):
    """
    Function parameter
    """

    key: str = "parameter_decl"


class Function(Entity, Named, Documented):
    """
    Function declarations
    """

    key: str = "function_decl"
    ret: Typespec
    parameters: typing.List[Parameter] = []


class FunctionPointer(Entity, Named, Documented):
    """
    Function pointer declarations by convention of::

        typedef int (*sym_)(int, int);

    Note..
    """

    key: str = "function_pointer_decl"
    ret: Typespec
    parameters: typing.List[Parameter] = []
