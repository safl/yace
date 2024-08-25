"""
For directives, currently just a placeholder for #include
"""

from pathlib import Path
from typing import Optional

from yace.idl.base import Entity


class IncludeDirective(Entity):
    """
    Something like::

      #include <stdio.h>
    """

    key: str = "include_stmt"
    filename: str
    resolved: Optional[Path] = None
