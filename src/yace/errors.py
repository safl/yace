#!/usr/bin/env python3
"""
YACE raises exceptions in case of error.

The errors are usually il-formated YAML-files, incorrect
:class:`yace.model.interface.Model`, type errors in the constructed
:class:`yace.model.interface.Model`, layout violations in the
:class:`yace.model.interface.Model`.
"""


class InvalidModelData(Exception):
    """The data given to entity instantion is not valid"""

    pass
