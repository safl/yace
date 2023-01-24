from yace.model.model import ModelWalker
from yace.model.structtypes import Bitfield, Bits, Field, Struct
from yace.model.uniontypes import Union


class HoistAnonMembers(ModelWalker):
    """Transforms the model"""

    def visit(self, current, ancestors, depth):
        if depth != 0:
            return (True, None)

        if not type(current) in [Struct, Union]:
            return (True, None)

        # TODO: top-level struct or union
