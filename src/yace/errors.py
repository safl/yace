#!/usr/bin/env python3
"""
YACE raises exceptions in case of error.

The errors are usually in-formated YAML-files, in-correct InterfaceModel, type
errors in the constructed InterfaceModel, layout violations in the
InterfaceModel.
"""


class InvalidInterfaceModelData(Exception):
    """The data given to entity instantion is not valid"""

    pass
