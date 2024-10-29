"""
For directives, currently just a placeholder for #include
"""

from yace.idl.base import Entity


class IncludeDirective(Entity):
    """
    Something like::

      #include <stdio.h>
    """

    key: str = "include_stmt"
    filename: str
