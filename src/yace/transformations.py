from yace.idl.derivedtypes import Struct, Union
from yace.model import ModelWalker


class HoistAnonMembers(ModelWalker):
    """Transforms the idl"""

    def visit(self, current, ancestors, depth):
        if depth != 0:
            return (True, None)

        if not type(current) in [Struct, Union]:
            return (True, None)

        # TODO: top-level struct or union
