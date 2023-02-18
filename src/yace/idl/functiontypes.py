#!/usr/bin/env python3
"""
The **yace** function types consists of:

* Function Declarations: :class:`.Function`
* Function Pointer Declarations: :class:`.FunctionPointer`
* Both of the above make use of

  * :class:`.Parameter`
  * :class:`.ReturnType`

Their idl representation follows below.
"""
import typing

from .base import Documented, Entity, Named, Typed


class ReturnType(Entity, Documented, Typed):
    """
    Function return type
    """

    cls: str = "ret"


class Parameter(Entity, Named, Documented, Typed):
    """
    Function parameter
    """

    cls: str = "param"


class Function(Entity, Named, Documented):
    """
    Function declarations
    """

    cls: str = "fun"
    ret: ReturnType

    parameters: typing.List[Parameter] = []


class FunctionPointer(Entity, Named, Documented, Typed):
    """
    Function pointer declarations
    """

    cls: str = "fun_ptr"
    ret: ReturnType

    parameters: typing.List[Parameter]
