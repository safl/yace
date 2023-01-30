from yace.idl.model import ModelWalker
from yace.idl.structtypes import Bitfield, Bits, Field, Struct
from yace.idl.uniontypes import Union


class HoistAnonMembers(ModelWalker):
    """Transforms the idl"""

    def visit(self, current, ancestors, depth):
        if depth != 0:
            return (True, None)

        if not type(current) in [Struct, Union]:
            return (True, None)

        # TODO: top-level struct or union
