#!/usr/bin/env python3
"""
YACE raises exceptions in case of error.

The errors are usually il-formated YAML-files, incorrect
:class:`yace.idl.interface.Model`, type errors in the constructed
:class:`yace.idl.interface.Model`, layout violations in the
:class:`yace.idl.interface.Model`.
"""


class TransformationError(Exception):
    """Something went wrong during a yid-transformation"""

    pass


class ToolError(Exception):
    """Exception raised when a tool exists with non-zero returncode"""

    pass


class InvalidModelData(Exception):
    """The data given to entity instantion is not valid"""

    pass
