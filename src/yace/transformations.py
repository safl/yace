"""
These are YIDL model transformations, transforming the loaded model into a
different representation, this is usually done in order to produce an
equivalent model with a representation better suited for emitting code.

E.g. symbols are snake_case in YIDL, however, when emitting Rust or Python
code, then it is very useful to have this transformed to CamelCase. By doings
so at the IDL-level, then the code-emitters need not concern inself with
UPPERCASE/lowercase/snake_case/camelCase/PascalCase etc. this makes emitters a
lot simpler.

Also, at the YIDL-level, then coding-conventions such as CamelCase can be
shared by multiple targets.
"""
from yace.idl.derivedtypes import Struct, Union
from yace.model import ModelWalker


class CStyle(ModelWalker):
    """
    Transform symbols:

    * :class:`yace.idl.constants.Define` -> upper()
    * :class:`yace.idl.constants.DefineValue` -> upper()

    This transformation assumes a valid YIDL according to the linter. Thus, the
    symbols are all lower-snake_case, and transformation not described above is
    not performed.
    """

    def visit(self, current, ancestors, depth):
        if depth != 0:
            return (True, None)

        if not type(current) in [Struct, Union]:
            return (True, None)


class Camelizer(ModelWalker):
    """
    Transform symbols:

    * Enum -> camelize()
    * EnumValue -> upper()
    * Struct|Enum|Bitfield -> camelize()

    This transformation assumes a valid YIDL according to the linter. Thus, the
    symbols are all lower-snake_case, and transformation not described above is
    not performed.
    """

    def visit(self, current, ancestors, depth):
        if depth != 0:
            return (True, None)

        if not type(current) in [Struct, Union]:
            return (True, None)



class HoistAnonMembers(ModelWalker):
    """
    Extract nested entities, that is, struct/union/bitfield which from nested
    to top-level declaration, leaving behind a replace of the entity with a
    field with a typespec matching the extracted entity"""

    def visit(self, current, ancestors, depth):
        if depth != 0:
            return (True, None)

        if type(current) not in [Struct, Union]:
            return (True, None)

        # TODO: top-level struct or union
